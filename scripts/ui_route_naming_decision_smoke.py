#!/usr/bin/env python3
"""Static smoke for the Gate 4 task/run route naming decision."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "docs" / "UI_ROUTE_NAMING_DECISION.json"
MATRIX_PATH = ROOT / "docs" / "UI_API_PARITY_MATRIX.json"
VITE_APP = ROOT / "ui" / "start-building-app"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "ui_route_naming_decision_v1"

REQUIRED_ROUTE_PAIRS = {
    "task_detail": {
        "legacy_route": "/admin/tasks/:id",
        "vite_target_route": "/workspace/tasks/:id",
        "target_route": "/workspace/tasks/:taskId",
        "next_alias_route": "/admin/tasks/:taskId",
    },
    "run_ledger": {
        "legacy_route": "/admin/runs",
        "vite_target_route": "/workspace/runs",
        "target_route": "/workspace/runs",
        "next_alias_route": "/admin/runs",
    },
    "run_detail": {
        "legacy_route": "/admin/runs/:id",
        "vite_target_route": "/workspace/runs/:id",
        "target_route": "/workspace/runs/:runId",
        "next_alias_route": "/admin/runs/:runId",
    },
}

REQUIRED_CUTOVER_ITEMS = {
    "route_level_read_model_parity",
    "vite_and_next_browser_snapshot_parity",
    "backward_compatible_redirect_or_alias",
    "navigation_inventory_update",
    "explicit_route_retirement_commit",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return json.loads(read_text(path))


def normalize_dynamic(route: str) -> str:
    route = route.replace("[...path]", ":path*")
    return re.sub(r"\[([A-Za-z0-9_]+)\]", r":\1", route)


def actual_vite_routes() -> set[str]:
    app_text = read_text(VITE_APP / "src" / "app" / "App.tsx")
    return set(re.findall(r"<Route\b[^>]*\bpath\s*=\s*['\"]([^'\"]+)['\"]", app_text, flags=re.S))


def next_page_route(path: Path) -> str:
    relative = path.relative_to(NEXT_APP / "app")
    parts = list(relative.parts[:-1])
    if not parts:
        return "/"
    return normalize_dynamic("/" + "/".join(parts))


def actual_next_routes() -> set[str]:
    return {next_page_route(path) for path in (NEXT_APP / "app").rglob("page.tsx")}


def matrix_entries_by_id() -> dict[str, dict[str, Any]]:
    matrix = read_json(MATRIX_PATH)
    entries = matrix.get("entries")
    require(isinstance(entries, list), "UI/API matrix entries must be a list")
    return {str(entry.get("id")): entry for entry in entries if isinstance(entry, dict)}


def assert_files_exist(paths: list[str], pair_id: str, field: str) -> None:
    require(isinstance(paths, list) and paths, f"{pair_id}.{field} must be a non-empty list")
    for item in paths:
        require((ROOT / item).exists(), f"{pair_id}.{field} references missing file: {item}")


def main() -> int:
    decision = read_json(DECISION_PATH)
    require(decision.get("contract_id") == CONTRACT_ID, f"contract_id must be {CONTRACT_ID}")
    require(decision.get("gate") == "gate_4_ui_api_parity_before_nextjs", "route naming decision is attached to the wrong gate")
    require(decision.get("status") == "accepted_task_run_workspace_redirect_retirement", "route naming decision must record the task/run retirement execution")

    policy = decision.get("policy") or {}
    require(policy.get("legacy_namespace") == "/admin", "legacy namespace must remain /admin")
    require(policy.get("target_namespace") == "/workspace", "target namespace must be /workspace")
    require(policy.get("legacy_owner") == "vite_react_redirect_alias", "legacy owner must be Vite redirect alias")
    require(policy.get("target_owner") == "nextjs_app_router", "target owner must be Next.js App Router")
    require(policy.get("alias_contract") == "ui_legacy_route_alias_v1", "route naming decision must bind the legacy alias contract")
    require(policy.get("navigation_inventory_contract") == "ui_navigation_inventory_v1", "route naming decision must bind the navigation inventory contract")
    require(policy.get("retirement_packet_contract") == "ui_route_retirement_packet_v1", "route naming decision must bind the retirement packet contract")
    require(policy.get("retirement_allowed_by_default") is False, "future route retirement must remain fail-closed by default")
    require(set(policy.get("executed_route_retirement_ids") or []) == set(REQUIRED_ROUTE_PAIRS), "task/run route retirements must be explicitly executed")
    require(policy.get("redirects_required_before_retirement") is True, "route retirement must require redirects or aliases")
    require(policy.get("no_breaking_deep_links") is True, "route retirement must preserve deep links")

    route_pairs = decision.get("route_pairs")
    require(isinstance(route_pairs, list), "route_pairs must be a list")
    pairs_by_id = {str(pair.get("id")): pair for pair in route_pairs if isinstance(pair, dict)}
    require(set(REQUIRED_ROUTE_PAIRS) <= set(pairs_by_id), f"missing route pairs: {sorted(set(REQUIRED_ROUTE_PAIRS) - set(pairs_by_id))}")

    vite_routes = actual_vite_routes()
    next_routes = actual_next_routes()
    entries = matrix_entries_by_id()

    for pair_id, expected in REQUIRED_ROUTE_PAIRS.items():
        pair = pairs_by_id[pair_id]
        legacy_route = expected["legacy_route"]
        vite_target_route = expected["vite_target_route"]
        target_route = expected["target_route"]
        next_alias_route = expected["next_alias_route"]
        require(pair.get("matrix_entry_id") == pair_id, f"{pair_id} must bind to its matrix entry")
        require(pair.get("legacy_route") == legacy_route, f"{pair_id} legacy route changed")
        require(pair.get("target_route") == target_route, f"{pair_id} target route changed")
        require(pair.get("next_alias_route") == next_alias_route, f"{pair_id} Next alias route changed")
        require(pair.get("decision") == "next_workspace_route_is_future_canonical", f"{pair_id} decision is not explicit")
        require(pair.get("legacy_route_status") == "redirects_to_target_route", f"{pair_id} legacy route status must be redirect-only")
        require(pair.get("next_alias_status") == "redirects_to_target_route", f"{pair_id} Next alias must redirect to target route")
        require(pair.get("target_route_status") == "workspace_canonical_route", f"{pair_id} target route status must identify workspace as canonical")
        require(pair.get("retirement_allowed") is True, f"{pair_id} must allow the executed route retirement")
        evidence = set(pair.get("cutover_evidence") or [])
        require("backward_compatible_redirect_or_alias" in evidence, f"{pair_id} must record redirect or alias cutover evidence")
        require("canonical_navigation_inventory_verified" in evidence, f"{pair_id} must record canonical navigation inventory evidence")
        require("retirement_packet_executed" in evidence, f"{pair_id} must record executed retirement packet evidence")
        require("vite_primary_links_migrated_to_workspace" in evidence, f"{pair_id} must record Vite primary link migration")
        require("agent_gateway_cli_api_mcp_unchanged" in evidence, f"{pair_id} must preserve Agent Gateway CLI/API/MCP")
        remaining = set(pair.get("remaining_cutover_requires") or [])
        require(not remaining, f"{pair_id} should not have remaining cutover requirements after this execution: {sorted(remaining)}")
        cutover = set(pair.get("cutover_requires") or [])
        require(REQUIRED_CUTOVER_ITEMS <= cutover, f"{pair_id} is missing cutover requirements: {sorted(REQUIRED_CUTOVER_ITEMS - cutover)}")
        assert_files_exist(pair.get("legacy_files") or [], pair_id, "legacy_files")
        assert_files_exist(pair.get("alias_files") or [], pair_id, "alias_files")
        assert_files_exist(pair.get("target_files") or [], pair_id, "target_files")

        require(legacy_route in vite_routes, f"{pair_id} legacy route is not implemented in Vite App.tsx: {legacy_route}")
        require(vite_target_route in vite_routes, f"{pair_id} Vite canonical workspace route is not implemented: {vite_target_route}")
        require(target_route in next_routes, f"{pair_id} target route is not implemented in Next app: {target_route}")
        require(next_alias_route in next_routes, f"{pair_id} Next alias route is not implemented: {next_alias_route}")

        matrix_entry = entries.get(pair_id)
        require(isinstance(matrix_entry, dict), f"matrix entry missing for {pair_id}")
        matrix_vite_routes = matrix_entry.get("vite_routes") or []
        matrix_next_routes = matrix_entry.get("next_routes") or []
        require(legacy_route in matrix_vite_routes, f"{pair_id} matrix vite routes must include naming decision route")
        require(vite_target_route in matrix_vite_routes, f"{pair_id} matrix vite routes must include Vite workspace target route")
        require(target_route in matrix_next_routes, f"{pair_id} matrix next routes must include naming decision route")
        require(next_alias_route in matrix_next_routes, f"{pair_id} matrix next routes must include legacy alias route")
        require(matrix_entry.get("retirement_allowed") is True, f"{pair_id} matrix retirement must be executed")
        require(matrix_entry.get("retirement_action") == "executed_workspace_redirect", f"{pair_id} matrix must record workspace redirect retirement")
        matrix_evidence = matrix_entry.get("evidence_commands") or []
        require("python3 scripts/ui_route_naming_decision_smoke.py" in matrix_evidence, f"{pair_id} matrix evidence must include route naming decision smoke")
        require("python3 scripts/ui_legacy_route_alias_smoke.py" in matrix_evidence, f"{pair_id} matrix evidence must include legacy route alias smoke")
        require("python3 scripts/ui_navigation_inventory_smoke.py" in matrix_evidence, f"{pair_id} matrix evidence must include navigation inventory smoke")
        require("python3 scripts/ui_route_retirement_packet_smoke.py" in matrix_evidence, f"{pair_id} matrix evidence must include route retirement packet smoke")

    md_text = read_text(ROOT / "docs" / "UI_ROUTE_NAMING_DECISION.md")
    require(CONTRACT_ID in md_text, "human route naming doc must name the contract")
    for expected in REQUIRED_ROUTE_PAIRS.values():
        require(
            expected["legacy_route"] in md_text and expected["target_route"] in md_text and expected["next_alias_route"] in md_text,
            "human route naming doc must list every route pair and alias",
        )

    closed_loop_text = read_text(ROOT / "docs" / "COMMERCIAL_MIGRATION_CLOSED_LOOP.md")
    readiness_text = read_text(ROOT / "scripts" / "commercial_migration_readiness.py")
    require("scripts/ui_route_naming_decision_smoke.py" in closed_loop_text, "closed-loop doc must include route naming decision smoke")
    require("scripts/ui_legacy_route_alias_smoke.py" in closed_loop_text, "closed-loop doc must include legacy route alias smoke")
    require("scripts/ui_navigation_inventory_smoke.py" in closed_loop_text, "closed-loop doc must include navigation inventory smoke")
    require("scripts/ui_route_retirement_packet_smoke.py" in closed_loop_text, "closed-loop doc must include route retirement packet smoke")
    require(CONTRACT_ID in readiness_text, "readiness checker must require the route naming decision contract")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "status": decision.get("status"),
        "route_pairs": sorted(REQUIRED_ROUTE_PAIRS),
        "retirement_allowed": True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
