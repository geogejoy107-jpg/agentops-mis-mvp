#!/usr/bin/env python3
"""Static smoke for covered route retirement candidates that remain fail-closed."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKET_PATH = ROOT / "docs" / "UI_COVERED_ROUTE_RETIREMENT_PACKET.json"
MATRIX_PATH = ROOT / "docs" / "UI_API_PARITY_MATRIX.json"
VITE_APP = ROOT / "ui" / "start-building-app"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "ui_covered_route_retirement_packet_v1"

REQUIRED_ROUTES = {
    "control_tower": {
        "legacy_vite_route": "/admin",
        "canonical_next_routes": ["/workspace", "/workspace/agents", "/workspace/governance", "/workspace/deployment"],
        "next_alias_route": None,
        "current_state": "covered_split_next_routes_no_admin_alias",
        "remaining_cutover_requires": {"admin_deep_link_redirect_or_alias", "explicit_route_retirement_commit"},
        "focused_smoke": "python3 scripts/nextjs_control_tower_parity_smoke.py",
        "matrix_gate_fragments": ["split-route control tower proof", "Vite /admin remains"],
        "source_files": [
            "ui/start-building-app/src/app/components/pages/ControlTower.tsx",
            "ui/next-app/src/components/WorkspaceDashboard.tsx",
            "ui/next-app/src/components/GovernancePage.tsx",
            "ui/next-app/src/components/DeploymentPage.tsx",
        ],
        "ui_markers": ["control-tower-split-proof", "route retirement blocked"],
    },
    "worker_console": {
        "legacy_vite_route": "/workspace/agents",
        "canonical_next_routes": ["/workspace/agents", "/workspace/workers"],
        "next_alias_route": "/workspace/agents",
        "current_state": "covered_same_path_plus_focused_worker_console",
        "remaining_cutover_requires": {"same_path_ownership_cutover_commit", "explicit_route_retirement_commit"},
        "focused_smoke": "python3 scripts/nextjs_worker_console_parity_smoke.py",
        "matrix_gate_fragments": ["Worker Console coverage boundary", "Agent Gateway CLI/API/MCP remains canonical"],
        "source_files": [
            "ui/start-building-app/src/app/components/pages/AIEmployees.tsx",
            "ui/next-app/src/components/AgentsParityPage.tsx",
            "ui/next-app/src/components/WorkerConsolePage.tsx",
        ],
        "ui_markers": ["worker-console-coverage-boundary", "Vite route retirement blocked"],
    },
}

REQUIRED_EVIDENCE_COMMANDS = {
    "python3 scripts/ui_api_parity_matrix_smoke.py",
    "python3 scripts/ui_covered_route_retirement_packet_smoke.py",
    "python3 scripts/nextjs_control_tower_parity_smoke.py",
    "python3 scripts/nextjs_worker_console_parity_smoke.py",
    "python3 scripts/vite_playwright_snapshot_smoke.py",
    "python3 scripts/nextjs_playwright_snapshot_smoke.py",
    "python3 scripts/nextjs_parity_smoke.py",
    "cd ui/start-building-app && npm run build",
    "cd ui/next-app && npm run build",
}

REQUIRED_COMMIT_EVIDENCE = {
    "route_pair_named_in_commit",
    "deep_link_redirect_or_alias_preserved",
    "matrix_retirement_decision_updated",
    "vite_and_next_browser_evidence_re_run",
    "agent_gateway_cli_api_mcp_unchanged",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
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


def main() -> int:
    packet = read_json(PACKET_PATH)
    require(packet.get("contract_id") == CONTRACT_ID, f"packet contract_id must be {CONTRACT_ID}")
    require(packet.get("gate") == "gate_4_ui_api_parity_before_nextjs", "packet gate id is wrong")
    require(packet.get("status") == "candidate_ready_no_route_retirement", "packet must be candidate-only")
    policy = packet.get("policy") or {}
    require(policy.get("scope") == "covered_control_tower_and_worker_console_routes", "packet scope is wrong")
    require(policy.get("retirement_action") == "not_executed", "packet must not execute retirement")
    require(policy.get("retirement_allowed") is False, "packet must keep retirement fail-closed")
    require(policy.get("candidate_only") is True, "packet must be candidate-only")
    require(policy.get("requires_explicit_route_retirement_commit") is True, "packet must require explicit retirement commit")
    require(policy.get("no_breaking_deep_links") is True, "packet must preserve deep links")
    require(policy.get("agent_gateway_cli_api_mcp_unchanged") is True, "packet must preserve Agent Gateway CLI/API/MCP")
    require(policy.get("verification_command") == "python3 scripts/ui_covered_route_retirement_packet_smoke.py", "packet verification command is wrong")

    evidence_commands = set(packet.get("evidence_commands") or [])
    require(REQUIRED_EVIDENCE_COMMANDS <= evidence_commands, f"packet misses evidence commands: {sorted(REQUIRED_EVIDENCE_COMMANDS - evidence_commands)}")
    checklist_text = "\n".join(map(str, packet.get("retirement_commit_checklist") or []))
    require("Agent Gateway CLI/API/MCP" in checklist_text, "packet must preserve Agent Gateway contract")
    require("raw prompts" in checklist_text and "secrets" in checklist_text, "packet must forbid sensitive/generated artifacts")

    matrix = read_json(MATRIX_PATH)
    route_contracts = set((matrix.get("policy") or {}).get("route_level_contracts") or [])
    require(CONTRACT_ID in route_contracts, "UI/API matrix must include the covered-route retirement packet contract")
    matrix_entries = {str(entry.get("id")): entry for entry in matrix.get("entries") or [] if isinstance(entry, dict)}

    vite_routes = actual_vite_routes()
    next_routes = actual_next_routes()
    packet_routes = {str(route.get("id")): route for route in packet.get("candidate_routes") or [] if isinstance(route, dict)}
    require(set(REQUIRED_ROUTES) == set(packet_routes), f"packet candidate routes changed: {sorted(packet_routes)}")

    for route_id, expected in REQUIRED_ROUTES.items():
        route = packet_routes[route_id]
        require(route.get("legacy_vite_route") == expected["legacy_vite_route"], f"{route_id} legacy route changed")
        require(route.get("canonical_next_routes") == expected["canonical_next_routes"], f"{route_id} canonical routes changed")
        require(route.get("next_alias_route") == expected["next_alias_route"], f"{route_id} alias route changed")
        require(route.get("current_state") == expected["current_state"], f"{route_id} current state is wrong")
        require(route.get("retirement_allowed_now") is False, f"{route_id} must not be retired by this packet")
        require(route.get("explicit_commit_required") is True, f"{route_id} must require an explicit retirement commit")
        require(expected["remaining_cutover_requires"] <= set(route.get("remaining_cutover_requires") or []), f"{route_id} misses remaining cutover requirements")
        require(REQUIRED_COMMIT_EVIDENCE <= set(route.get("required_commit_evidence") or []), f"{route_id} misses commit evidence requirements")

        require(expected["legacy_vite_route"] in vite_routes, f"{route_id} Vite legacy route is already missing")
        for next_route in expected["canonical_next_routes"]:
            require(next_route in next_routes, f"{route_id} Next canonical route is missing: {next_route}")

        matrix_entry = matrix_entries.get(route_id) or {}
        require(matrix_entry.get("status") == "covered", f"{route_id} matrix entry must be covered")
        require(matrix_entry.get("retirement_allowed") is False, f"{route_id} matrix must remain fail-closed")
        matrix_evidence = set(matrix_entry.get("evidence_commands") or [])
        require(expected["focused_smoke"] in matrix_evidence, f"{route_id} matrix must include focused smoke")
        require("python3 scripts/ui_covered_route_retirement_packet_smoke.py" in matrix_evidence, f"{route_id} matrix must include covered-route packet smoke")
        gate = str(matrix_entry.get("retirement_gate") or "")
        for fragment in expected["matrix_gate_fragments"]:
            require(fragment in gate, f"{route_id} retirement gate missing {fragment!r}")
        require("explicit route retirement commit" in gate, f"{route_id} must still require explicit retirement commit")

        for source in expected["source_files"]:
            read_text(ROOT / source)
        combined_source = "\n".join(read_text(ROOT / source) for source in expected["source_files"])
        for marker in expected["ui_markers"]:
            require(marker in combined_source, f"{route_id} source marker missing: {marker}")

    human_doc = read_text(ROOT / "docs" / "UI_COVERED_ROUTE_RETIREMENT_PACKET.md")
    matrix_doc = read_text(ROOT / "docs" / "UI_API_PARITY_MATRIX.md")
    closed_loop = read_text(ROOT / "docs" / "COMMERCIAL_MIGRATION_CLOSED_LOOP.md")
    parity_smoke = read_text(ROOT / "scripts" / "nextjs_parity_smoke.py")
    readiness = read_text(ROOT / "scripts" / "commercial_migration_readiness.py")
    require(CONTRACT_ID in human_doc, "human packet doc must name the contract")
    require("does not retire any Vite route" in human_doc, "human packet doc must keep route retirement fail-closed")
    require(CONTRACT_ID in matrix_doc, "matrix doc must reference the covered-route packet contract")
    require("scripts/ui_covered_route_retirement_packet_smoke.py" in closed_loop, "closed-loop doc must include covered-route packet smoke")
    require(CONTRACT_ID in parity_smoke, "Next static parity smoke must require the covered-route packet")
    require(CONTRACT_ID in readiness, "readiness checker must require the covered-route packet")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "candidate_routes": sorted(REQUIRED_ROUTES),
        "retirement_action": "not_executed",
        "retirement_allowed": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
