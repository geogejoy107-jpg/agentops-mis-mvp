#!/usr/bin/env python3
"""Static smoke for the Pixel Office / Dispatch route retirement evidence packet."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKET_PATH = ROOT / "docs" / "PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json"
PACKET_DOC_PATH = ROOT / "docs" / "PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.md"
MATRIX_PATH = ROOT / "docs" / "UI_API_PARITY_MATRIX.json"
MATRIX_DOC_PATH = ROOT / "docs" / "UI_API_PARITY_MATRIX.md"
VITE_APP = ROOT / "ui" / "start-building-app"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "pixel_office_dispatch_retirement_evidence_v1"
ENTRY_ID = "pixel_office_and_dispatch"

REQUIRED_NEXT_ROUTES = {
    "/workspace/pixel-office",
    "/workspace/pixel-office/local-brief",
    "/workspace/dispatch",
    "/workspace/dispatch/customer-task",
    "/workspace/dispatch/template-job",
    "/workspace/dispatch/template-run",
    "/workspace/dispatch/customer-worker",
    "/workspace/dispatch/customer-worker-job",
    "/workspace/reports",
    "/workspace/approvals",
    "/workspace/runs",
}

REQUIRED_BEHAVIOR_COMMANDS = {
    "python3 scripts/nextjs_pixel_office_floor_smoke.py",
    "python3 scripts/nextjs_pixel_office_dispatch_smoke.py",
    "python3 scripts/local_brief_prepared_action_smoke.py",
    "python3 scripts/nextjs_local_brief_smoke.py",
    "python3 scripts/nextjs_customer_worker_dispatch_smoke.py",
    "python3 scripts/nextjs_customer_worker_async_job_smoke.py",
    "python3 scripts/nextjs_customer_worker_prepared_action_smoke.py",
}

REQUIRED_API_CONTRACTS = {
    "GET /dashboard/metrics",
    "GET /agents",
    "GET /tasks",
    "POST /workflows/local-brief",
    "GET /workflows/customer-task-templates",
    "POST /workflows/customer-task-templates/run",
    "POST /workflows/customer-task-templates/submit",
    "POST /workflows/customer-task",
    "POST /workflows/customer-worker-task",
    "POST /workflows/customer-worker-task/submit",
    "GET /workflows/customer-worker-prepared-actions",
    "GET /workflows/jobs",
    "GET /workflows/jobs/:job_id",
}

REQUIRED_COMMIT_EVIDENCE = {
    "route_pair_named_in_commit",
    "deep_link_redirect_or_alias_preserved",
    "matrix_retirement_decision_updated",
    "vite_and_next_browser_evidence_re_run",
    "agent_gateway_contract_unchanged",
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


def next_route(path: Path) -> str:
    relative = path.relative_to(NEXT_APP / "app")
    return normalize_dynamic("/" + "/".join(relative.parts[:-1]))


def actual_next_routes() -> set[str]:
    routes: set[str] = set()
    for path in (NEXT_APP / "app").rglob("page.tsx"):
        routes.add(next_route(path))
    for path in (NEXT_APP / "app").rglob("route.ts"):
        routes.add(next_route(path))
    return routes


def actual_vite_routes() -> set[str]:
    app_text = read_text(VITE_APP / "src" / "app" / "App.tsx")
    return set(re.findall(r"<Route\b[^>]*\bpath\s*=\s*['\"]([^'\"]+)['\"]", app_text, flags=re.S))


def main() -> int:
    packet = read_json(PACKET_PATH)
    require(packet.get("contract_id") == CONTRACT_ID, f"contract_id must be {CONTRACT_ID}")
    require(packet.get("gate") == "gate_4_ui_api_parity_before_nextjs", "gate id is wrong")
    require(packet.get("status") == "visual_evidence_ready_no_route_retirement", "packet status is wrong")
    policy = packet.get("policy") or {}
    require(policy.get("scope") == ENTRY_ID, "packet scope must be pixel_office_and_dispatch")
    require(policy.get("retirement_action") == "not_executed", "packet must not execute retirement")
    require(policy.get("retirement_allowed") is False, "packet must keep retirement fail-closed")
    require(policy.get("candidate_only") is True, "packet must be candidate-only")
    require(policy.get("requires_explicit_route_retirement_commit") is True, "packet must require explicit retirement commit")
    require(policy.get("vite_canonical_until_explicit_commit") is True, "packet must keep Vite canonical until explicit commit")
    require(policy.get("no_breaking_deep_links") is True, "packet must preserve deep links")
    require(policy.get("verification_command") == "python3 scripts/pixel_office_dispatch_retirement_evidence_smoke.py", "wrong verification command")

    route_pair = packet.get("route_pair") or {}
    require(route_pair.get("id") == ENTRY_ID, "route pair id is wrong")
    require(route_pair.get("legacy_vite_route") == "/workspace/pixel-office", "legacy Vite route changed")
    require(set(route_pair.get("canonical_next_routes") or []) >= REQUIRED_NEXT_ROUTES, "missing canonical Next routes")
    require(route_pair.get("current_state") == "vite_route_kept_next_visual_evidence_ready", "current state is wrong")
    require(route_pair.get("retirement_allowed_now") is False, "route pair must not be retired")
    require(route_pair.get("explicit_commit_required") is True, "route pair must require explicit commit")
    require(set(route_pair.get("remaining_cutover_requires") or []) == {"explicit_route_retirement_commit"}, "remaining cutover gate is wrong")
    require(REQUIRED_COMMIT_EVIDENCE <= set(route_pair.get("required_commit_evidence") or []), "missing required commit evidence")

    require("/workspace/pixel-office" in actual_vite_routes(), "Vite Pixel Office route is missing")
    require(REQUIRED_NEXT_ROUTES <= actual_next_routes(), "Next route files do not match the packet")

    visual = packet.get("visual_evidence") or {}
    vite_visual = visual.get("vite") or {}
    next_visual = visual.get("next") or {}
    require(vite_visual.get("command") == "python3 scripts/vite_playwright_snapshot_smoke.py", "wrong Vite visual command")
    require(vite_visual.get("route") == "/workspace/pixel-office", "wrong Vite visual route")
    require(next_visual.get("command") == "python3 scripts/nextjs_playwright_snapshot_smoke.py", "wrong Next visual command")
    require(set(next_visual.get("routes") or []) >= {"/workspace/pixel-office", "/workspace/dispatch"}, "Next visual routes missing")

    vite_smoke = read_text(ROOT / "scripts" / "vite_playwright_snapshot_smoke.py")
    next_smoke = read_text(ROOT / "scripts" / "nextjs_playwright_snapshot_smoke.py")
    for text in vite_visual.get("required_visible_text") or []:
        require(str(text) in vite_smoke, f"Vite visual evidence missing expected text {text!r}")
    for text in next_visual.get("required_visible_text") or []:
        require(str(text) in next_smoke, f"Next visual evidence missing expected text {text!r}")
    require("leaked_secret" in vite_smoke and "leaked_secret" in next_smoke, "browser evidence must check token leakage")

    behavior_commands = set(packet.get("next_behavior_evidence") or [])
    require(REQUIRED_BEHAVIOR_COMMANDS <= behavior_commands, f"missing behavior evidence: {sorted(REQUIRED_BEHAVIOR_COMMANDS - behavior_commands)}")
    api_contracts = set(packet.get("api_contracts") or [])
    require(REQUIRED_API_CONTRACTS <= api_contracts, f"missing API contracts: {sorted(REQUIRED_API_CONTRACTS - api_contracts)}")
    omission = packet.get("omission_contract") or {}
    for key in ("token_omitted", "raw_prompt_omitted", "raw_response_omitted", "raw_private_transcript_omitted"):
        require(omission.get(key) is True, f"omission contract must require {key}")
    require(omission.get("local_database_committed") is False, "packet must forbid committing local DBs")
    require(omission.get("generated_artifacts_committed") is False, "packet must forbid committing generated artifacts")

    checklist = "\n".join(map(str, packet.get("retirement_commit_checklist") or []))
    require("Agent Gateway CLI/API/MCP" in checklist, "checklist must preserve Agent Gateway")
    require("raw prompts" in checklist and "secrets" in checklist, "checklist must forbid sensitive material")

    matrix = read_json(MATRIX_PATH)
    route_contracts = set((matrix.get("policy") or {}).get("route_level_contracts") or [])
    require(CONTRACT_ID in route_contracts, "UI/API matrix policy must include the Pixel retirement evidence contract")
    entries = {str(entry.get("id")): entry for entry in matrix.get("entries") or [] if isinstance(entry, dict)}
    entry = entries.get(ENTRY_ID) or {}
    require(entry.get("status") == "covered", "pixel_office_and_dispatch should be covered after explicit visual evidence packet")
    require(entry.get("retirement_allowed") is False, "pixel_office_and_dispatch retirement must remain fail-closed")
    require("python3 scripts/pixel_office_dispatch_retirement_evidence_smoke.py" in set(entry.get("evidence_commands") or []), "matrix entry must include this smoke")
    require(CONTRACT_ID in str(entry.get("retirement_gate") or ""), "matrix retirement gate must name this contract")
    require("explicit route retirement commit" in str(entry.get("retirement_gate") or ""), "matrix must still require explicit retirement commit")

    human_doc = read_text(PACKET_DOC_PATH)
    matrix_doc = read_text(MATRIX_DOC_PATH)
    closed_loop = read_text(ROOT / "docs" / "COMMERCIAL_MIGRATION_CLOSED_LOOP.md")
    readiness = read_text(ROOT / "scripts" / "commercial_migration_readiness.py")
    require(CONTRACT_ID in human_doc, "human packet doc must name the contract")
    require("does not retire the Vite" in human_doc, "human packet doc must keep retirement fail-closed")
    require(CONTRACT_ID in matrix_doc, "matrix doc must reference the Pixel evidence contract")
    require("pixel_office_dispatch_retirement_evidence_smoke.py" in closed_loop, "closed-loop doc must include this smoke")
    require(CONTRACT_ID in readiness, "readiness checker must require this contract")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "route_pair": ENTRY_ID,
        "retirement_action": "not_executed",
        "retirement_allowed": False,
        "status": "visual_evidence_ready_no_route_retirement",
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
