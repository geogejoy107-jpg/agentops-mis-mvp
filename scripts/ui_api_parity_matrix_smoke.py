#!/usr/bin/env python3
"""Static smoke for the Gate 4 Vite/Next UI/API parity matrix."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "docs" / "UI_API_PARITY_MATRIX.json"
VITE_APP = ROOT / "ui" / "start-building-app"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "ui_api_parity_matrix_v1"

STATUS_VALUES = {"covered", "partial", "next_only", "deferred"}
GATE4_REQUIRED_IDS = {
    "pixel_office_and_dispatch",
    "worker_console",
    "agent_detail",
    "reports",
    "approvals",
    "memory",
    "audit",
    "customer_project_report",
    "task_list",
    "task_detail",
    "run_ledger",
    "run_detail",
    "tool_calls",
    "evaluation_room",
    "runtime_connectors",
    "external_bases_notion",
    "next_mis_proxy",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_matrix() -> dict:
    require(MATRIX_PATH.exists(), f"missing matrix: {MATRIX_PATH.relative_to(ROOT)}")
    return json.loads(read_text(MATRIX_PATH))


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


def next_handler_route(path: Path) -> str:
    relative = path.relative_to(NEXT_APP / "app")
    parts = list(relative.parts[:-1])
    return normalize_dynamic("/" + "/".join(parts))


def actual_next_routes() -> set[str]:
    routes: set[str] = set()
    for path in (NEXT_APP / "app").rglob("page.tsx"):
        routes.add(next_page_route(path))
    for path in (NEXT_APP / "app").rglob("route.ts"):
        routes.add(next_handler_route(path))
    return routes


def relative_paths_exist(paths: list[str], entry_id: str, field: str) -> None:
    for item in paths:
        require((ROOT / item).exists(), f"{entry_id}.{field} references missing file: {item}")


def api_contract_fragments(contract: str) -> list[str]:
    if "->" in contract:
        return ["AGENTOPS_API_BASE"] if "AGENTOPS_API_BASE" in contract else []
    parts = contract.split(maxsplit=1)
    if len(parts) != 2:
        return []
    path = parts[1]
    fragments: list[str] = []
    if path.startswith("/"):
        first_dynamic = re.search(r"[:*]", path)
        prefix = path[:first_dynamic.start()] if first_dynamic else path
        prefix = prefix.rstrip("/")
        if prefix:
            fragments.append(prefix)
    for token in re.findall(r"/([A-Za-z0-9_-]+)(?=/|$|\?)", path):
        if not token.startswith(":") and token not in {"api"}:
            fragments.append(token)
    return sorted(set(fragments), key=len, reverse=True)


def source_text_for(paths: list[str]) -> str:
    chunks = []
    for item in paths:
        path = ROOT / item
        if path.exists():
            chunks.append(read_text(path))
    return "\n".join(chunks)


def assert_entry_routes(entry: dict | None, entry_id: str, vite_routes: list[str], next_routes: list[str]) -> None:
    require(isinstance(entry, dict), f"missing matrix entry for {entry_id}")
    actual_vite = set(entry.get("vite_routes") or [])
    actual_next = set(entry.get("next_routes") or [])
    require(set(vite_routes) <= actual_vite, f"{entry_id}.vite_routes must include {vite_routes}")
    require(set(next_routes) <= actual_next, f"{entry_id}.next_routes must include {next_routes}")
    require(entry.get("retirement_allowed") is False, f"{entry_id} must stay blocked from retirement until a naming/navigation decision exists")


def main() -> int:
    matrix = load_matrix()
    require(matrix.get("contract_id") == CONTRACT_ID, f"matrix contract_id must be {CONTRACT_ID}")
    require(matrix.get("gate") == "gate_4_ui_api_parity_before_nextjs", "matrix gate id is wrong")
    require(matrix.get("policy", {}).get("canonical_ui") == "vite_react", "matrix must keep Vite as canonical UI")
    require(matrix.get("policy", {}).get("migration_track") == "nextjs_app_router", "matrix must name the Next.js migration track")
    route_contracts = matrix.get("policy", {}).get("route_level_contracts") or []
    require("ui_route_naming_decision_v1" in route_contracts, "matrix policy must include the route naming decision contract")
    require("ui_legacy_route_alias_v1" in route_contracts, "matrix policy must include the legacy route alias contract")
    require("ui_navigation_inventory_v1" in route_contracts, "matrix policy must include the navigation inventory contract")
    require("ui_route_retirement_packet_v1" in route_contracts, "matrix policy must include the route retirement packet contract")
    require("nextjs_agent_gateway_task_proxy_v1" in route_contracts, "matrix policy must include the Next Gateway task proxy contract")
    require("nextjs_agent_gateway_cli_worker_dogfood_v1" in route_contracts, "matrix policy must include the Next Gateway CLI worker dogfood contract")
    require("nextjs_worker_dispatch_once_v1" in route_contracts, "matrix policy must include the Next worker dispatch contract")
    require("nextjs_pixel_office_floor_v1" in route_contracts, "matrix policy must include the Next Pixel Office floor contract")
    require("local_brief_prepared_action_v1" in route_contracts, "matrix policy must include the local brief backend prepared-action contract")
    require("nextjs_local_brief_v1" in route_contracts, "matrix policy must include the Next local brief contract")
    require("nextjs_customer_worker_dispatch_v1" in route_contracts, "matrix policy must include the Next customer-worker dispatch contract")
    require("nextjs_customer_worker_async_job_v1" in route_contracts, "matrix policy must include the Next customer-worker async job contract")
    require("nextjs_worker_stuck_release_v1" in route_contracts, "matrix policy must include the Next worker stuck release contract")
    require("nextjs_enrollment_request_v1" in route_contracts, "matrix policy must include the Next enrollment request contract")
    require("nextjs_worker_daemon_control_v1" in route_contracts, "matrix policy must include the Next worker daemon control contract")

    entries = matrix.get("entries")
    require(isinstance(entries, list) and entries, "matrix entries must be a non-empty list")

    ids: set[str] = set()
    entries_by_id: dict[str, dict] = {}
    matrix_vite_routes: set[str] = set()
    matrix_next_routes: set[str] = set()
    gate4_required: set[str] = set()
    retired: list[str] = []
    status_counts: dict[str, int] = {status: 0 for status in STATUS_VALUES}

    for entry in entries:
        entry_id = str(entry.get("id") or "")
        require(entry_id, "matrix entry is missing id")
        require(entry_id not in ids, f"duplicate matrix id: {entry_id}")
        ids.add(entry_id)
        entries_by_id[entry_id] = entry

        status = str(entry.get("status") or "")
        require(status in STATUS_VALUES, f"{entry_id} has invalid status: {status}")
        status_counts[status] += 1

        capability = str(entry.get("capability") or "")
        require(capability, f"{entry_id} is missing capability")
        retirement_gate = str(entry.get("retirement_gate") or "")
        require(retirement_gate, f"{entry_id} is missing retirement_gate")

        is_gate4_required = bool(entry.get("gate4_required"))
        if is_gate4_required:
            gate4_required.add(entry_id)

        if entry.get("retirement_allowed"):
            retired.append(entry_id)

        vite_routes = entry.get("vite_routes") or []
        next_routes = entry.get("next_routes") or []
        api_contracts = entry.get("api_contracts") or []
        evidence = entry.get("evidence_commands") or []
        require(isinstance(vite_routes, list), f"{entry_id}.vite_routes must be a list")
        require(isinstance(next_routes, list), f"{entry_id}.next_routes must be a list")
        require(isinstance(api_contracts, list), f"{entry_id}.api_contracts must be a list")
        require(isinstance(evidence, list) and evidence, f"{entry_id}.evidence_commands must be a non-empty list")

        if status in {"covered", "partial"}:
            require(vite_routes, f"{entry_id} is {status} but has no Vite route")
            require(next_routes, f"{entry_id} is {status} but has no Next route")
        if status == "next_only":
            require(next_routes and not vite_routes, f"{entry_id} is next_only but route ownership is ambiguous")
        if status == "deferred":
            require(vite_routes and not next_routes, f"{entry_id} is deferred but should remain Vite-only")
        if is_gate4_required:
            require(api_contracts, f"{entry_id} needs at least one API contract because it is Gate 4 required")

        relative_paths_exist(entry.get("vite_files") or [], entry_id, "vite_files")
        relative_paths_exist(entry.get("next_files") or [], entry_id, "next_files")
        if is_gate4_required and api_contracts:
            source = source_text_for((entry.get("vite_files") or []) + (entry.get("next_files") or []))
            for contract in map(str, api_contracts):
                fragments = api_contract_fragments(contract)
                require(fragments, f"{entry_id} has an API contract that cannot be checked: {contract}")
                missing = [fragment for fragment in fragments if fragment not in source]
                require(not missing, f"{entry_id} API contract {contract!r} misses source fragments: {missing}")

        matrix_vite_routes.update(map(str, vite_routes))
        matrix_next_routes.update(map(str, next_routes))

    require(not retired, f"no Vite routes may be retired in this gate slice; found {retired}")
    require(GATE4_REQUIRED_IDS.issubset(gate4_required), f"missing Gate 4 required ids: {sorted(GATE4_REQUIRED_IDS - gate4_required)}")
    vite_smoke_text = read_text(ROOT / "scripts" / "vite_playwright_snapshot_smoke.py")
    require("snapshot_vite_detail_routes" in vite_smoke_text, "Vite browser smoke must include task/run detail snapshot coverage")
    require("/admin/tasks/" in vite_smoke_text and "/admin/runs/" in vite_smoke_text, "Vite browser smoke must navigate task/run admin detail routes")
    for detail_id in ("task_detail", "run_detail"):
        evidence = entries_by_id.get(detail_id, {}).get("evidence_commands") or []
        require("python3 scripts/vite_playwright_snapshot_smoke.py" in evidence, f"{detail_id} must include Vite browser detail snapshot evidence")
    for route_id in ("task_detail", "run_ledger", "run_detail"):
        evidence = entries_by_id.get(route_id, {}).get("evidence_commands") or []
        require("python3 scripts/ui_route_naming_decision_smoke.py" in evidence, f"{route_id} must include route naming decision evidence")
        require("python3 scripts/ui_legacy_route_alias_smoke.py" in evidence, f"{route_id} must include legacy route alias evidence")
        require("python3 scripts/ui_navigation_inventory_smoke.py" in evidence, f"{route_id} must include navigation inventory evidence")
        require("python3 scripts/ui_route_retirement_packet_smoke.py" in evidence, f"{route_id} must include route retirement packet evidence")
    assert_entry_routes(entries_by_id.get("task_detail"), "task_detail", ["/admin/tasks/:id"], ["/workspace/tasks/:taskId"])
    assert_entry_routes(entries_by_id.get("run_ledger"), "run_ledger", ["/admin/runs"], ["/workspace/runs"])
    assert_entry_routes(entries_by_id.get("run_detail"), "run_detail", ["/admin/runs/:id"], ["/workspace/runs/:runId"])
    assert_entry_routes(entries_by_id.get("agent_detail"), "agent_detail", ["/admin/agents/:id"], ["/workspace/agents/:agentId"])
    agent_detail_evidence = entries_by_id.get("agent_detail", {}).get("evidence_commands") or []
    require("python3 scripts/nextjs_parity_smoke.py" in agent_detail_evidence, "agent_detail must include Next static parity evidence")
    require("python3 scripts/nextjs_playwright_snapshot_smoke.py" in agent_detail_evidence, "agent_detail must include Next browser evidence")
    worker_console_evidence = entries_by_id.get("worker_console", {}).get("evidence_commands") or []
    require("python3 scripts/nextjs_worker_dispatch_once_smoke.py" in worker_console_evidence, "worker_console must include Next worker dispatch mutation evidence")
    require("python3 scripts/nextjs_worker_stuck_release_smoke.py" in worker_console_evidence, "worker_console must include Next worker stuck release mutation evidence")
    require("python3 scripts/nextjs_enrollment_request_smoke.py" in worker_console_evidence, "worker_console must include Next approval-gated enrollment request evidence")
    require("python3 scripts/nextjs_worker_daemon_control_smoke.py" in worker_console_evidence, "worker_console must include Next mock worker daemon control evidence")
    worker_console_gate = str(entries_by_id.get("worker_console", {}).get("retirement_gate") or "")
    require("mock_only_next_parity" in worker_console_gate, "worker_console retirement gate must record non-mock dispatch fail-closed evidence")
    require("mock_daemon_only_next_parity" in worker_console_gate, "worker_console retirement gate must record non-mock daemon fail-closed evidence")
    require("live_worker_daemon_not_allowed_next_parity" in worker_console_gate, "worker_console retirement gate must record live daemon fail-closed evidence")
    require("force_release_not_allowed_next_parity" in worker_console_gate, "worker_console retirement gate must record force-release fail-closed evidence")
    require("enrollment_token_issue_not_allowed_next_parity" in worker_console_gate, "worker_console retirement gate must record raw enrollment token issue fail-closed evidence")
    assert_entry_routes(entries_by_id.get("pixel_office_and_dispatch"), "pixel_office_and_dispatch", ["/workspace/pixel-office"], ["/workspace/pixel-office", "/workspace/pixel-office/local-brief", "/workspace/dispatch", "/workspace/dispatch/template-run", "/workspace/dispatch/customer-worker", "/workspace/dispatch/customer-worker-job"])
    pixel_dispatch_evidence = entries_by_id.get("pixel_office_and_dispatch", {}).get("evidence_commands") or []
    require("python3 scripts/nextjs_pixel_office_floor_smoke.py" in pixel_dispatch_evidence, "pixel_office_and_dispatch must include Next Pixel Office floor evidence")
    require("python3 scripts/local_brief_prepared_action_smoke.py" in pixel_dispatch_evidence, "pixel_office_and_dispatch must include local brief prepared-action backend evidence")
    require("python3 scripts/nextjs_local_brief_smoke.py" in pixel_dispatch_evidence, "pixel_office_and_dispatch must include Next local brief prepared-action evidence")
    require("python3 scripts/nextjs_customer_worker_dispatch_smoke.py" in pixel_dispatch_evidence, "pixel_office_and_dispatch must include Next customer-worker dispatch mutation evidence")
    require("python3 scripts/nextjs_customer_worker_async_job_smoke.py" in pixel_dispatch_evidence, "pixel_office_and_dispatch must include Next customer-worker async job evidence")
    pixel_dispatch_gate = str(entries_by_id.get("pixel_office_and_dispatch", {}).get("retirement_gate") or "")
    require("read-only Pixel Operating Map" in pixel_dispatch_gate, "pixel_office_and_dispatch retirement gate must record Next Pixel Office floor evidence")
    require("local-brief prepared-action exact resume" in pixel_dispatch_gate, "pixel_office_and_dispatch retirement gate must record Next local brief prepared-action evidence")
    require("mock-only customer-worker dispatch" in pixel_dispatch_gate, "pixel_office_and_dispatch retirement gate must record mock-only customer-worker dispatch evidence")
    require("mock-only async customer-worker job" in pixel_dispatch_gate, "pixel_office_and_dispatch retirement gate must record mock-only async customer-worker job evidence")
    assert_entry_routes(entries_by_id.get("tool_calls"), "tool_calls", ["/admin/toolcalls"], ["/workspace/tool-calls"])
    tool_call_evidence = entries_by_id.get("tool_calls", {}).get("evidence_commands") or []
    require("python3 scripts/nextjs_parity_smoke.py" in tool_call_evidence, "tool_calls must include Next static parity evidence")
    require("python3 scripts/nextjs_playwright_snapshot_smoke.py" in tool_call_evidence, "tool_calls must include Next browser evidence")
    assert_entry_routes(entries_by_id.get("evaluation_room"), "evaluation_room", ["/admin/evaluations"], ["/workspace/evaluations"])
    evaluation_evidence = entries_by_id.get("evaluation_room", {}).get("evidence_commands") or []
    require("python3 scripts/nextjs_parity_smoke.py" in evaluation_evidence, "evaluation_room must include Next static parity evidence")
    require("python3 scripts/nextjs_playwright_snapshot_smoke.py" in evaluation_evidence, "evaluation_room must include Next browser evidence")
    assert_entry_routes(entries_by_id.get("runtime_connectors"), "runtime_connectors", ["/admin/connectors"], ["/workspace/connectors", "/workspace/connectors/trust"])
    connector_evidence = entries_by_id.get("runtime_connectors", {}).get("evidence_commands") or []
    require("python3 scripts/nextjs_parity_smoke.py" in connector_evidence, "runtime_connectors must include Next static parity evidence")
    require("python3 scripts/nextjs_playwright_snapshot_smoke.py" in connector_evidence, "runtime_connectors must include Next browser evidence")
    assert_entry_routes(entries_by_id.get("external_bases_notion"), "external_bases_notion", ["/admin/bases/notion"], ["/workspace/external-bases/notion", "/workspace/external-bases/notion/export"])
    notion_evidence = entries_by_id.get("external_bases_notion", {}).get("evidence_commands") or []
    require("python3 scripts/nextjs_parity_smoke.py" in notion_evidence, "external_bases_notion must include Next static parity evidence")
    require("python3 scripts/nextjs_playwright_snapshot_smoke.py" in notion_evidence, "external_bases_notion must include Next browser evidence")
    next_proxy_evidence = entries_by_id.get("next_mis_proxy", {}).get("evidence_commands") or []
    require("python3 scripts/nextjs_agent_gateway_task_proxy_smoke.py" in next_proxy_evidence, "next_mis_proxy must include Next Gateway task proxy evidence")
    require("python3 scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py" in next_proxy_evidence, "next_mis_proxy must include Next Gateway CLI worker dogfood evidence")
    require("python3 scripts/nextjs_customer_worker_dispatch_smoke.py" in next_proxy_evidence, "next_mis_proxy must include Next customer-worker dispatch proxy evidence")
    require("python3 scripts/nextjs_customer_worker_async_job_smoke.py" in next_proxy_evidence, "next_mis_proxy must include Next customer-worker async job proxy evidence")
    require("python3 scripts/nextjs_enrollment_request_smoke.py" in next_proxy_evidence, "next_mis_proxy must include Next enrollment proxy guard evidence")

    vite_routes = actual_vite_routes()
    next_routes = actual_next_routes()
    require(vite_routes <= matrix_vite_routes, f"matrix misses Vite routes: {sorted(vite_routes - matrix_vite_routes)}")
    require(next_routes <= matrix_next_routes, f"matrix misses Next routes: {sorted(next_routes - matrix_next_routes)}")

    doc_text = read_text(ROOT / "docs" / "UI_API_PARITY_MATRIX.md")
    migration_text = read_text(ROOT / "docs" / "COMMERCIAL_MIGRATION_CLOSED_LOOP.md")
    require(CONTRACT_ID in doc_text, "human matrix doc must name the contract id")
    require("scripts/ui_api_parity_matrix_smoke.py" in doc_text, "human matrix doc must name the smoke")
    require("UI_API_PARITY_MATRIX" in migration_text, "closed-loop doc must link the UI/API parity matrix")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "entries": len(entries),
        "status_counts": status_counts,
        "vite_routes": sorted(vite_routes),
        "next_routes": sorted(next_routes),
        "retirement_allowed": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
