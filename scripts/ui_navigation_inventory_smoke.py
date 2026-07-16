#!/usr/bin/env python3
"""Static smoke for workspace navigation inventory."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NEXT_APP = ROOT / "ui" / "next-app"
VITE_APP = ROOT / "ui" / "start-building-app"
INVENTORY_PATH = ROOT / "docs" / "UI_NAVIGATION_INVENTORY.json"
DECISION_PATH = ROOT / "docs" / "UI_ROUTE_NAMING_DECISION.json"
MATRIX_PATH = ROOT / "docs" / "UI_API_PARITY_MATRIX.json"
CONTRACT_ID = "ui_navigation_inventory_v1"

CANONICAL_NEXT_ROUTES = {
    "/workspace/tasks",
    "/workspace/tasks/:taskId",
    "/workspace/runs",
    "/workspace/runs/:runId",
    "/workspace/agents/:agentId",
    "/workspace/evaluations",
    "/workspace/tool-calls",
    "/workspace/connectors",
    "/workspace/external-bases/notion",
    "/workspace/templates",
    "/workspace/audit",
}
ALLOWED_ALIAS_ROUTES = {
    "/admin/tasks/:taskId",
    "/admin/runs",
    "/admin/runs/:runId",
}
REQUIRED_INVENTORY_FILES = {
    "ui/next-app/src/components/AppFrame.tsx",
    "ui/next-app/src/components/LedgerPages.tsx",
    "ui/next-app/src/components/LedgerDetailPages.tsx",
    "ui/next-app/src/components/EvidencePage.tsx",
}
ALIAS_FILES = {
    "ui/next-app/app/admin/tasks/[taskId]/page.tsx",
    "ui/next-app/app/admin/runs/page.tsx",
    "ui/next-app/app/admin/runs/[runId]/page.tsx",
}
CANONICAL_VITE_ROUTES = {
    "/workspace/tasks",
    "/workspace/tasks/:id",
    "/workspace/runs",
    "/workspace/runs/:id",
    "/workspace/agents/:id",
    "/workspace/evaluations",
    "/workspace/tool-calls",
    "/workspace/connectors",
    "/workspace/external-bases/notion",
    "/workspace/templates",
    "/workspace/audit",
}
ALLOWED_VITE_ALIAS_ROUTES = {
    "/admin/tasks/:id",
    "/admin/runs",
    "/admin/runs/:id",
    "/admin/agents/:id",
    "/admin/evaluations",
    "/admin/toolcalls",
    "/admin/connectors",
    "/admin/bases/notion",
    "/admin/templates",
    "/admin/audit",
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


def next_page_route(path: Path) -> str:
    relative = path.relative_to(NEXT_APP / "app")
    parts = list(relative.parts[:-1])
    if not parts:
        return "/"
    return normalize_dynamic("/" + "/".join(parts))


def actual_next_pages() -> set[str]:
    return {next_page_route(path) for path in (NEXT_APP / "app").rglob("page.tsx")}


def actual_vite_routes() -> set[str]:
    app_text = read_text(VITE_APP / "src" / "app" / "App.tsx")
    return set(re.findall(r"<Route\b[^>]*\bpath\s*=\s*['\"]([^'\"]+)['\"]", app_text, flags=re.S))


def next_primary_source_files() -> list[Path]:
    files: list[Path] = []
    for base in (NEXT_APP / "app", NEXT_APP / "src"):
        for path in base.rglob("*"):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            relative = path.relative_to(NEXT_APP)
            if relative.parts[:2] == ("app", "admin"):
                continue
            files.append(path)
    return sorted(files)


def assert_no_primary_admin_task_run_links() -> list[str]:
    violations: list[str] = []
    pattern = re.compile(r"/admin/(?:tasks|runs)(?:/|[\"'`<\s)]|$)")
    for path in next_primary_source_files():
        text = read_text(path)
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            violations.append(f"{path.relative_to(ROOT)}:{line}:{match.group(0)}")
    return violations


def assert_no_vite_primary_admin_task_run_links() -> list[str]:
    violations: list[str] = []
    pattern = re.compile(r"/admin/(?:tasks|runs)(?:/|[\"'`<\s)]|$)")
    for path in sorted((VITE_APP / "src" / "app" / "components").rglob("*")):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = read_text(path)
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            violations.append(f"{path.relative_to(ROOT)}:{line}:{match.group(0)}")
    return violations


def assert_no_vite_primary_admin_operations_links() -> list[str]:
    violations: list[str] = []
    pattern = re.compile(r"/admin/(?:agents|evaluations|toolcalls|connectors|bases/notion|templates|audit)(?:/|[\"'`<\s)]|$)")
    for path in sorted((VITE_APP / "src" / "app" / "components").rglob("*")):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = read_text(path)
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            violations.append(f"{path.relative_to(ROOT)}:{line}:{match.group(0)}")
    return violations


def main() -> int:
    inventory = read_json(INVENTORY_PATH)
    require(inventory.get("contract_id") == CONTRACT_ID, f"inventory contract_id must be {CONTRACT_ID}")
    require(inventory.get("gate") == "gate_4_ui_api_parity_before_nextjs", "inventory gate id is wrong")
    require(inventory.get("status") == "accepted_admin_operations_workspace_redirect_retirement", "inventory must record workspace route retirement execution")
    policy = inventory.get("policy") or {}
    require(policy.get("next_primary_namespace") == "/workspace", "Next primary namespace must be /workspace")
    require(policy.get("vite_primary_namespace") == "/workspace", "Vite primary namespace must be /workspace for retired routes")
    require(policy.get("legacy_namespace") == "/admin", "legacy namespace must be /admin")
    require(policy.get("legacy_admin_usage_in_next") == "redirect_alias_only", "Next /admin usage must be redirect-alias only")
    require(policy.get("legacy_admin_usage_in_vite") == "redirect_alias_only", "Vite /admin usage must be redirect-alias only")
    require(policy.get("admin_operations_contract") == "ui_admin_operations_route_retirement_v1", "inventory must bind the admin operations contract")
    require(policy.get("retirement_allowed") is True, "inventory must allow the executed route retirement")
    require(policy.get("verification_command") == "python3 scripts/ui_navigation_inventory_smoke.py", "inventory verification command is wrong")

    require(set(inventory.get("canonical_next_routes") or []) == CANONICAL_NEXT_ROUTES, "canonical Next workspace routes changed")
    require(set(inventory.get("allowed_next_alias_routes") or []) == ALLOWED_ALIAS_ROUTES, "allowed Next alias routes changed")
    require(set(inventory.get("canonical_vite_routes") or []) == CANONICAL_VITE_ROUTES, "canonical Vite workspace routes changed")
    require(set(inventory.get("allowed_vite_alias_routes") or []) == ALLOWED_VITE_ALIAS_ROUTES, "allowed Vite alias routes changed")
    require(set(inventory.get("next_primary_inventory_files") or []) >= REQUIRED_INVENTORY_FILES, "inventory misses primary Next files")
    require(set(inventory.get("next_alias_files") or []) == ALIAS_FILES, "inventory alias file list changed")
    require(inventory.get("legacy_vite_inventory_status") == "redirect_alias_only_after_explicit_retirement_commit", "Vite legacy inventory must be redirect-only")
    require(inventory.get("remaining_cutover_requires") == [], "navigation inventory should have no remaining task/run cutover requirements")

    for item in REQUIRED_INVENTORY_FILES | ALIAS_FILES:
        require((ROOT / item).exists(), f"inventory references missing file: {item}")

    app_frame_text = read_text(ROOT / "ui/next-app/src/components/AppFrame.tsx")
    ledger_pages_text = read_text(ROOT / "ui/next-app/src/components/LedgerPages.tsx")
    detail_pages_text = read_text(ROOT / "ui/next-app/src/components/LedgerDetailPages.tsx")
    evidence_text = read_text(ROOT / "ui/next-app/src/components/EvidencePage.tsx")
    require('href: "/workspace/tasks"' in app_frame_text, "Next primary nav must link to /workspace/tasks")
    require('href: "/workspace/runs"' in app_frame_text, "Next primary nav must link to /workspace/runs")
    require("/workspace/tasks/${encodeURIComponent(task.task_id)}" in ledger_pages_text, "Next task rows must link to workspace task detail")
    require("/workspace/runs/${encodeURIComponent(run.run_id)}" in ledger_pages_text, "Next run rows must link to workspace run detail")
    require("/workspace/runs/${encodeURIComponent(run.run_id)}" in detail_pages_text, "Next task detail must link related runs through workspace")
    require("/workspace/tasks/${encodeURIComponent(taskIdForLink)}" in detail_pages_text, "Next run detail must link back to task through workspace")
    require("/workspace/runs/" in evidence_text and "/workspace/tasks/" in evidence_text, "Next evidence drilldown must link task/run through workspace")

    aliases = {
        "task_detail": read_text(ROOT / "ui/next-app/app/admin/tasks/[taskId]/page.tsx"),
        "run_ledger": read_text(ROOT / "ui/next-app/app/admin/runs/page.tsx"),
        "run_detail": read_text(ROOT / "ui/next-app/app/admin/runs/[runId]/page.tsx"),
    }
    require("/workspace/tasks/${encodeURIComponent(taskId)}" in aliases["task_detail"], "task alias must redirect to workspace task detail")
    require('redirect("/workspace/runs")' in aliases["run_ledger"], "run ledger alias must redirect to workspace runs")
    require("/workspace/runs/${encodeURIComponent(runId)}" in aliases["run_detail"], "run alias must redirect to workspace run detail")

    violations = assert_no_primary_admin_task_run_links()
    require(not violations, "Next primary source contains task/run /admin links: " + ", ".join(violations))
    vite_violations = assert_no_vite_primary_admin_task_run_links()
    require(not vite_violations, "Vite primary source contains task/run /admin links: " + ", ".join(vite_violations))
    vite_admin_ops_violations = assert_no_vite_primary_admin_operations_links()
    require(not vite_admin_ops_violations, "Vite primary source contains admin operations /admin links: " + ", ".join(vite_admin_ops_violations))

    next_pages = actual_next_pages()
    require(CANONICAL_NEXT_ROUTES <= next_pages, f"Next app misses canonical task/run pages: {sorted(CANONICAL_NEXT_ROUTES - next_pages)}")
    require(ALLOWED_ALIAS_ROUTES <= next_pages, f"Next app misses allowed task/run alias pages: {sorted(ALLOWED_ALIAS_ROUTES - next_pages)}")
    vite_routes = actual_vite_routes()
    require(CANONICAL_VITE_ROUTES <= vite_routes, f"Vite app misses canonical task/run routes: {sorted(CANONICAL_VITE_ROUTES - vite_routes)}")
    require(ALLOWED_VITE_ALIAS_ROUTES <= vite_routes, f"Vite app misses allowed task/run alias routes: {sorted(ALLOWED_VITE_ALIAS_ROUTES - vite_routes)}")
    vite_app_text = read_text(VITE_APP / "src" / "app" / "App.tsx")
    require("LegacyTaskDetailRedirect" in vite_app_text and "LegacyRunDetailRedirect" in vite_app_text and "LegacyAgentDetailRedirect" in vite_app_text, "Vite app must preserve admin deep links with redirect components")
    for target in ("/workspace/evaluations", "/workspace/tool-calls", "/workspace/connectors", "/workspace/external-bases/notion", "/workspace/templates", "/workspace/audit"):
        require(target in vite_app_text, f"Vite legacy admin operations route must redirect to {target}")

    decision_text = read_text(DECISION_PATH)
    matrix_text = read_text(MATRIX_PATH)
    readiness_text = read_text(ROOT / "scripts" / "commercial_migration_readiness.py")
    closed_loop_text = read_text(ROOT / "docs" / "COMMERCIAL_MIGRATION_CLOSED_LOOP.md")
    require(CONTRACT_ID in decision_text, "route naming decision must reference navigation inventory contract")
    require(CONTRACT_ID in matrix_text, "UI/API matrix must reference navigation inventory contract")
    require("ui_admin_operations_route_retirement_v1" in matrix_text, "UI/API matrix must reference admin operations contract")
    require(CONTRACT_ID in readiness_text, "readiness checker must require navigation inventory contract")
    require("scripts/ui_navigation_inventory_smoke.py" in closed_loop_text, "closed-loop doc must include navigation inventory smoke")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "canonical_next_routes": sorted(CANONICAL_NEXT_ROUTES),
        "canonical_vite_routes": sorted(CANONICAL_VITE_ROUTES),
        "allowed_next_alias_routes": sorted(ALLOWED_ALIAS_ROUTES),
        "allowed_vite_alias_routes": sorted(ALLOWED_VITE_ALIAS_ROUTES),
        "admin_operations_retired": True,
        "retirement_allowed": True,
        "remaining_cutover_requires": [],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
