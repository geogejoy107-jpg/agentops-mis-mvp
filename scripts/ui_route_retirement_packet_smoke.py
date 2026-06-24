#!/usr/bin/env python3
"""Static smoke for the Gate 4 task/run route retirement packet."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKET_PATH = ROOT / "docs" / "UI_ROUTE_RETIREMENT_PACKET.json"
DECISION_PATH = ROOT / "docs" / "UI_ROUTE_NAMING_DECISION.json"
MATRIX_PATH = ROOT / "docs" / "UI_API_PARITY_MATRIX.json"
VITE_APP = ROOT / "ui" / "start-building-app"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "ui_route_retirement_packet_v1"

REQUIRED_ROUTES = {
    "task_detail": {
        "legacy_vite_route": "/admin/tasks/:id",
        "canonical_vite_route": "/workspace/tasks/:id",
        "canonical_next_route": "/workspace/tasks/:taskId",
        "next_alias_route": "/admin/tasks/:taskId",
        "alias_file": "ui/next-app/app/admin/tasks/[taskId]/page.tsx",
        "alias_target_fragment": "/workspace/tasks/${encodeURIComponent(taskId)}",
    },
    "run_ledger": {
        "legacy_vite_route": "/admin/runs",
        "canonical_vite_route": "/workspace/runs",
        "canonical_next_route": "/workspace/runs",
        "next_alias_route": "/admin/runs",
        "alias_file": "ui/next-app/app/admin/runs/page.tsx",
        "alias_target_fragment": 'redirect("/workspace/runs")',
    },
    "run_detail": {
        "legacy_vite_route": "/admin/runs/:id",
        "canonical_vite_route": "/workspace/runs/:id",
        "canonical_next_route": "/workspace/runs/:runId",
        "next_alias_route": "/admin/runs/:runId",
        "alias_file": "ui/next-app/app/admin/runs/[runId]/page.tsx",
        "alias_target_fragment": "/workspace/runs/${encodeURIComponent(runId)}",
    },
}

REQUIRED_EVIDENCE_COMMANDS = {
    "python3 scripts/ui_api_parity_matrix_smoke.py",
    "python3 scripts/ui_task_run_route_parity_smoke.py",
    "python3 scripts/ui_route_naming_decision_smoke.py",
    "python3 scripts/ui_legacy_route_alias_smoke.py",
    "python3 scripts/ui_navigation_inventory_smoke.py",
    "python3 scripts/ui_route_retirement_packet_smoke.py",
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


def main() -> int:
    packet = read_json(PACKET_PATH)
    require(packet.get("contract_id") == CONTRACT_ID, f"packet contract_id must be {CONTRACT_ID}")
    require(packet.get("gate") == "gate_4_ui_api_parity_before_nextjs", "packet gate id is wrong")
    require(packet.get("status") == "executed_task_run_workspace_redirect_retirement", "packet must record executed task/run route retirement")
    policy = packet.get("policy") or {}
    require(policy.get("scope") == "task_run_legacy_admin_routes", "packet scope is wrong")
    require(policy.get("retirement_action") == "executed_workspace_redirect", "packet must execute workspace redirect retirement")
    require(policy.get("retirement_allowed") is True, "packet must allow the executed task/run retirement")
    require(policy.get("candidate_only") is False, "packet must no longer be candidate-only")
    require(policy.get("requires_explicit_route_retirement_commit") is False, "packet must close the explicit retirement requirement")
    require(policy.get("no_breaking_deep_links") is True, "packet must preserve deep links")
    require(set(policy.get("executed_route_ids") or []) == set(REQUIRED_ROUTES), "packet must name the executed task/run route ids")
    require(policy.get("agent_gateway_cli_api_mcp_unchanged") is True, "packet must preserve Agent Gateway CLI/API/MCP")
    require(policy.get("verification_command") == "python3 scripts/ui_route_retirement_packet_smoke.py", "packet verification command is wrong")

    evidence_commands = set(packet.get("evidence_commands") or [])
    require(REQUIRED_EVIDENCE_COMMANDS <= evidence_commands, f"packet misses evidence commands: {sorted(REQUIRED_EVIDENCE_COMMANDS - evidence_commands)}")
    checklist_text = "\n".join(map(str, packet.get("retirement_commit_checklist") or []))
    require("Agent Gateway CLI/API/MCP" in checklist_text, "packet must preserve Agent Gateway contract")
    require("raw prompts" in checklist_text and "secrets" in checklist_text, "packet must forbid sensitive/generated artifacts")

    decision = read_json(DECISION_PATH)
    decision_policy = decision.get("policy") or {}
    require(decision_policy.get("retirement_packet_contract") == CONTRACT_ID, "route naming decision must bind the retirement packet contract")
    matrix = read_json(MATRIX_PATH)
    matrix_policy = matrix.get("policy") or {}
    route_contracts = set(matrix_policy.get("route_level_contracts") or [])
    require(CONTRACT_ID in route_contracts, "UI/API matrix must include the retirement packet contract")

    vite_routes = actual_vite_routes()
    next_routes = actual_next_routes()
    vite_app_text = read_text(VITE_APP / "src" / "app" / "App.tsx")
    matrix_entries = {str(entry.get("id")): entry for entry in matrix.get("entries") or [] if isinstance(entry, dict)}
    decision_pairs = {str(pair.get("id")): pair for pair in decision.get("route_pairs") or [] if isinstance(pair, dict)}
    packet_routes = {str(route.get("id")): route for route in packet.get("candidate_routes") or [] if isinstance(route, dict)}
    require(set(REQUIRED_ROUTES) == set(packet_routes), f"packet candidate routes changed: {sorted(packet_routes)}")

    for route_id, expected in REQUIRED_ROUTES.items():
        route = packet_routes[route_id]
        require(route.get("legacy_vite_route") == expected["legacy_vite_route"], f"{route_id} legacy route changed")
        require(route.get("canonical_next_route") == expected["canonical_next_route"], f"{route_id} canonical route changed")
        require(route.get("next_alias_route") == expected["next_alias_route"], f"{route_id} alias route changed")
        require(route.get("current_state") == "vite_legacy_route_redirects_to_workspace_next_alias_ready", f"{route_id} current state is wrong")
        require(route.get("retirement_allowed_now") is True, f"{route_id} must be retired by this packet")
        require(route.get("explicit_commit_required") is False, f"{route_id} must close the explicit retirement requirement")
        require(route.get("retirement_action") == "executed_workspace_redirect", f"{route_id} must record workspace redirect retirement")
        require(REQUIRED_COMMIT_EVIDENCE <= set(route.get("required_commit_evidence") or []), f"{route_id} misses commit evidence requirements")
        require("agent_gateway_cli_api_mcp_unchanged" in set(route.get("executed_evidence") or []), f"{route_id} must preserve Agent Gateway CLI/API/MCP")

        require(expected["legacy_vite_route"] in vite_routes, f"{route_id} Vite legacy route is already missing")
        require(expected["canonical_vite_route"] in vite_routes, f"{route_id} Vite canonical workspace route is missing")
        require(expected["canonical_next_route"] in next_routes, f"{route_id} Next canonical route is missing")
        require(expected["next_alias_route"] in next_routes, f"{route_id} Next alias route is missing")
        alias_file = ROOT / expected["alias_file"]
        require(alias_file.exists(), f"{route_id} alias file is missing")
        require(expected["alias_target_fragment"] in read_text(alias_file), f"{route_id} alias no longer redirects to canonical target")

        decision_pair = decision_pairs.get(route_id) or {}
        require(decision_pair.get("retirement_allowed") is True, f"{route_id} route decision must record executed retirement")
        require(decision_pair.get("legacy_route_status") == "redirects_to_target_route", f"{route_id} route decision must make the legacy route redirect-only")
        require("retirement_packet_executed" in set(decision_pair.get("cutover_evidence") or []), f"{route_id} route decision must record executed packet evidence")
        require("vite_primary_links_migrated_to_workspace" in set(decision_pair.get("cutover_evidence") or []), f"{route_id} route decision must record Vite primary link migration")
        require(set(decision_pair.get("remaining_cutover_requires") or []) == set(), f"{route_id} should have no remaining route cutover requirements")

        matrix_entry = matrix_entries.get(route_id) or {}
        require(matrix_entry.get("retirement_allowed") is True, f"{route_id} matrix must record executed retirement")
        require(matrix_entry.get("retirement_action") == "executed_workspace_redirect", f"{route_id} matrix must record workspace redirect retirement")
        matrix_evidence = set(matrix_entry.get("evidence_commands") or [])
        require("python3 scripts/ui_route_retirement_packet_smoke.py" in matrix_evidence, f"{route_id} matrix must include packet smoke")
        gate = str(matrix_entry.get("retirement_gate") or "").lower()
        require("explicit route retirement executed" in gate and "redirect" in gate, f"{route_id} retirement gate must record executed redirect retirement")

    require("LegacyTaskDetailRedirect" in vite_app_text and "LegacyRunDetailRedirect" in vite_app_text, "Vite legacy task/run deep links must be redirect components")
    require('<Route path="/admin/runs" element={<Navigate to="/workspace/runs" replace />} />' in vite_app_text, "Vite legacy run ledger must redirect to workspace runs")

    human_doc = read_text(ROOT / "docs" / "UI_ROUTE_RETIREMENT_PACKET.md")
    route_doc = read_text(ROOT / "docs" / "UI_ROUTE_NAMING_DECISION.md")
    matrix_doc = read_text(ROOT / "docs" / "UI_API_PARITY_MATRIX.md")
    closed_loop = read_text(ROOT / "docs" / "COMMERCIAL_MIGRATION_CLOSED_LOOP.md")
    readiness = read_text(ROOT / "scripts" / "commercial_migration_readiness.py")
    require(CONTRACT_ID in human_doc, "human packet doc must name the contract")
    require("redirect-only deep links" in human_doc, "human packet doc must record executed route retirement")
    require(CONTRACT_ID in route_doc, "route naming doc must reference the packet contract")
    require(CONTRACT_ID in matrix_doc, "matrix doc must reference the packet contract")
    require("scripts/ui_route_retirement_packet_smoke.py" in closed_loop, "closed-loop doc must include packet smoke")
    require(CONTRACT_ID in readiness, "readiness checker must require the packet contract")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "candidate_routes": sorted(REQUIRED_ROUTES),
        "retirement_action": "executed_workspace_redirect",
        "retirement_allowed": True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
