#!/usr/bin/env python3
"""Static smoke for the Gate 4 admin operations route retirement slice."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VITE_APP = ROOT / "ui" / "start-building-app"
NEXT_APP = ROOT / "ui" / "next-app"
MATRIX_PATH = ROOT / "docs" / "UI_API_PARITY_MATRIX.json"
DECISION_PATH = ROOT / "docs" / "UI_ROUTE_NAMING_DECISION.json"
INVENTORY_PATH = ROOT / "docs" / "UI_NAVIGATION_INVENTORY.json"
RETIREMENT_PACKET_PATH = ROOT / "docs" / "UI_ROUTE_RETIREMENT_PACKET.json"
CONTRACT_ID = "ui_admin_operations_route_retirement_v1"
SMOKE_COMMAND = "python3 scripts/ui_admin_operations_route_retirement_smoke.py"

ADMIN_OPERATION_ROUTES = {
    "agent_detail": {
        "legacy_vite_route": "/admin/agents/:id",
        "canonical_vite_route": "/workspace/agents/:id",
        "canonical_next_route": "/workspace/agents/:agentId",
        "redirect_fragment": "LegacyAgentDetailRedirect",
    },
    "evaluation_room": {
        "legacy_vite_route": "/admin/evaluations",
        "canonical_vite_route": "/workspace/evaluations",
        "canonical_next_route": "/workspace/evaluations",
        "redirect_fragment": 'to="/workspace/evaluations"',
    },
    "tool_calls": {
        "legacy_vite_route": "/admin/toolcalls",
        "canonical_vite_route": "/workspace/tool-calls",
        "canonical_next_route": "/workspace/tool-calls",
        "redirect_fragment": 'to="/workspace/tool-calls"',
    },
    "runtime_connectors": {
        "legacy_vite_route": "/admin/connectors",
        "canonical_vite_route": "/workspace/connectors",
        "canonical_next_route": "/workspace/connectors",
        "redirect_fragment": 'to="/workspace/connectors"',
    },
    "external_bases_notion": {
        "legacy_vite_route": "/admin/bases/notion",
        "canonical_vite_route": "/workspace/external-bases/notion",
        "canonical_next_route": "/workspace/external-bases/notion",
        "redirect_fragment": 'to="/workspace/external-bases/notion"',
    },
    "template_switching": {
        "legacy_vite_route": "/admin/templates",
        "canonical_vite_route": "/workspace/templates",
        "canonical_next_route": "/workspace/templates",
        "redirect_fragment": 'to="/workspace/templates"',
    },
    "audit": {
        "legacy_vite_route": "/admin/audit",
        "canonical_vite_route": "/workspace/audit",
        "canonical_next_route": "/workspace/audit",
        "redirect_fragment": 'to="/workspace/audit"',
    },
}

ADMIN_OPERATION_PATTERN = re.compile(
    r"/admin/(?:agents|evaluations|toolcalls|connectors|bases/notion|templates|audit)(?:/|[\"'`<\s)]|$)"
)


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


def actual_next_pages() -> set[str]:
    return {next_page_route(path) for path in (NEXT_APP / "app").rglob("page.tsx")}


def assert_no_primary_admin_operation_links() -> list[str]:
    violations: list[str] = []
    for path in sorted((VITE_APP / "src" / "app" / "components").rglob("*")):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = read_text(path)
        for match in ADMIN_OPERATION_PATTERN.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            violations.append(f"{path.relative_to(ROOT)}:{line}:{match.group(0)}")
    return violations


def main() -> int:
    vite_routes = actual_vite_routes()
    next_pages = actual_next_pages()
    app_text = read_text(VITE_APP / "src" / "app" / "App.tsx")
    matrix = read_json(MATRIX_PATH)
    decision = read_json(DECISION_PATH)
    inventory = read_json(INVENTORY_PATH)
    packet = read_json(RETIREMENT_PACKET_PATH)

    require(CONTRACT_ID in set(matrix.get("policy", {}).get("route_level_contracts") or []), "matrix must include the admin operations route retirement contract")
    require(CONTRACT_ID in read_text(ROOT / "scripts" / "commercial_migration_readiness.py"), "readiness checker must require the admin operations contract")

    decision_policy = decision.get("policy") or {}
    require(CONTRACT_ID in set(decision_policy.get("route_level_contracts") or []), "route naming decision must bind the admin operations contract")
    require(set(ADMIN_OPERATION_ROUTES) <= set(decision_policy.get("executed_route_retirement_ids") or []), "decision must name every executed admin operations route")

    inventory_policy = inventory.get("policy") or {}
    require(inventory_policy.get("legacy_admin_usage_in_vite") == "redirect_alias_only", "Vite legacy admin operations must be redirect-only")
    require(set(route["canonical_vite_route"] for route in ADMIN_OPERATION_ROUTES.values()) <= set(inventory.get("canonical_vite_routes") or []), "inventory misses canonical Vite admin-ops workspace routes")
    require(set(route["legacy_vite_route"] for route in ADMIN_OPERATION_ROUTES.values()) <= set(inventory.get("allowed_vite_alias_routes") or []), "inventory misses legacy admin-ops aliases")

    packet_policy = packet.get("policy") or {}
    require(CONTRACT_ID in set(packet_policy.get("contracts") or []), "route retirement packet must include the admin operations contract")
    require(set(ADMIN_OPERATION_ROUTES) <= set(packet_policy.get("executed_route_ids") or []), "packet must name every executed admin operations route")
    require(packet_policy.get("agent_gateway_cli_api_mcp_unchanged") is True, "packet must preserve Agent Gateway CLI/API/MCP")

    matrix_entries = {str(entry.get("id")): entry for entry in matrix.get("entries") or [] if isinstance(entry, dict)}
    decision_pairs = {str(pair.get("id")): pair for pair in decision.get("route_pairs") or [] if isinstance(pair, dict)}
    packet_routes = {str(route.get("id")): route for route in packet.get("candidate_routes") or [] if isinstance(route, dict)}

    for route_id, expected in ADMIN_OPERATION_ROUTES.items():
        require(expected["legacy_vite_route"] in vite_routes, f"{route_id} legacy Vite route missing")
        require(expected["canonical_vite_route"] in vite_routes, f"{route_id} canonical Vite workspace route missing")
        require(expected["canonical_next_route"] in next_pages, f"{route_id} canonical Next workspace page missing")
        require(expected["redirect_fragment"] in app_text, f"{route_id} legacy route must redirect to workspace")

        entry = matrix_entries.get(route_id) or {}
        require(expected["legacy_vite_route"] in set(entry.get("vite_routes") or []), f"{route_id} matrix missing legacy Vite route")
        require(expected["canonical_vite_route"] in set(entry.get("vite_routes") or []), f"{route_id} matrix missing canonical Vite workspace route")
        require(expected["canonical_next_route"] in set(entry.get("next_routes") or []), f"{route_id} matrix missing canonical Next route")
        require(entry.get("retirement_allowed") is True, f"{route_id} matrix must record executed retirement")
        require(entry.get("retirement_action") == "executed_workspace_redirect", f"{route_id} matrix must record workspace redirect action")
        require(SMOKE_COMMAND in set(entry.get("evidence_commands") or []), f"{route_id} matrix evidence must include this contract smoke")

        pair = decision_pairs.get(route_id) or {}
        require(pair.get("legacy_route_status") == "redirects_to_target_route", f"{route_id} decision must make legacy route redirect-only")
        require(pair.get("target_route_status") == "workspace_canonical_route", f"{route_id} decision must make workspace route canonical")
        require(pair.get("retirement_allowed") is True, f"{route_id} decision must allow executed retirement")
        require(not pair.get("remaining_cutover_requires"), f"{route_id} should not have remaining cutover requirements")

        packet_route = packet_routes.get(route_id) or {}
        require(packet_route.get("retirement_action") == "executed_workspace_redirect", f"{route_id} packet must record executed redirect")
        require(packet_route.get("retirement_allowed_now") is True, f"{route_id} packet must allow executed retirement")
        require(packet_route.get("explicit_commit_required") is False, f"{route_id} packet must close explicit commit requirement")

    violations = assert_no_primary_admin_operation_links()
    require(not violations, "Vite primary source contains admin operations links: " + ", ".join(violations))

    covered_packet = read_json(ROOT / "docs" / "UI_COVERED_ROUTE_RETIREMENT_PACKET.json")
    covered_routes = {str(route.get("id")): route for route in covered_packet.get("candidate_routes") or [] if isinstance(route, dict)}
    for route_id in ("control_tower", "worker_console"):
        require(covered_routes.get(route_id, {}).get("retirement_allowed_now") is False, f"{route_id} must remain candidate-only")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "executed_admin_operation_routes": sorted(ADMIN_OPERATION_ROUTES),
        "retirement_action": "executed_workspace_redirect",
        "legacy_admin_usage_in_vite": "redirect_alias_only",
        "agent_gateway_cli_api_mcp_unchanged": True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
