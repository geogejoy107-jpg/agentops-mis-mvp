#!/usr/bin/env python3
"""Static smoke for the Next.js commercial parity track."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEXT_APP = ROOT / "ui" / "next-app"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    package_path = NEXT_APP / "package.json"
    package = json.loads(read_text(package_path))
    dependencies = package.get("dependencies", {})
    scripts = package.get("scripts", {})

    required_files = [
        NEXT_APP / "app" / "layout.tsx",
        NEXT_APP / "app" / "workspace" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "agents" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "tasks" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "runs" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "approvals" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "approvals" / "review" / "route.ts",
        NEXT_APP / "app" / "workspace" / "memory" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "memory" / "review" / "route.ts",
        NEXT_APP / "app" / "workspace" / "reports" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "customer-projects" / "[projectId]" / "report" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "customer-projects" / "[projectId]" / "report" / "archive" / "route.ts",
        NEXT_APP / "app" / "workspace" / "audit" / "page.tsx",
        NEXT_APP / "app" / "api" / "mis" / "[...path]" / "route.ts",
        NEXT_APP / "src" / "components" / "AppFrame.tsx",
        NEXT_APP / "src" / "components" / "AgentsParityPage.tsx",
        NEXT_APP / "src" / "components" / "DeliveryPages.tsx",
        NEXT_APP / "src" / "components" / "LedgerPages.tsx",
        NEXT_APP / "src" / "components" / "GovernancePages.tsx",
        NEXT_APP / "src" / "components" / "WorkspaceDashboard.tsx",
        NEXT_APP / "src" / "lib" / "mis.ts",
        NEXT_APP / "src" / "lib" / "misServer.ts",
        NEXT_APP / "src" / "styles" / "globals.css",
    ]

    for path in required_files:
        require(path.exists(), f"missing Next.js parity file: {path.relative_to(ROOT)}")

    route_text = read_text(NEXT_APP / "app" / "api" / "mis" / "[...path]" / "route.ts")
    approvals_review_route_text = read_text(NEXT_APP / "app" / "workspace" / "approvals" / "review" / "route.ts")
    memory_review_route_text = read_text(NEXT_APP / "app" / "workspace" / "memory" / "review" / "route.ts")
    report_archive_route_text = read_text(NEXT_APP / "app" / "workspace" / "customer-projects" / "[projectId]" / "report" / "archive" / "route.ts")
    app_frame_text = read_text(NEXT_APP / "src" / "components" / "AppFrame.tsx")
    agents_page_text = read_text(NEXT_APP / "src" / "components" / "AgentsParityPage.tsx")
    delivery_pages_text = read_text(NEXT_APP / "src" / "components" / "DeliveryPages.tsx")
    ledger_pages_text = read_text(NEXT_APP / "src" / "components" / "LedgerPages.tsx")
    governance_pages_text = read_text(NEXT_APP / "src" / "components" / "GovernancePages.tsx")
    dashboard_text = read_text(NEXT_APP / "src" / "components" / "WorkspaceDashboard.tsx")
    lib_text = read_text(NEXT_APP / "src" / "lib" / "mis.ts")
    server_lib_text = read_text(NEXT_APP / "src" / "lib" / "misServer.ts")

    require(dependencies.get("next") == "16.2.9", "Next.js version is not pinned to the selected migration version")
    require(dependencies.get("react") == "19.2.7", "React version is not pinned to the selected migration version")
    require("build" in scripts and "next build" in scripts["build"], "Next.js build script is missing")
    require("AGENTOPS_API_BASE" in route_text, "API proxy must be configurable with AGENTOPS_API_BASE")
    require("AGENTOPS_API_BASE" in server_lib_text and "loadServerApprovals" in server_lib_text, "server-side first paint loaders are missing")
    require("/dashboard/metrics" in lib_text, "workspace parity data must include dashboard metrics")
    require("/tasks" in lib_text and "/runs" in lib_text and "/approvals" in lib_text, "workspace parity data misses core ledgers")
    require("/memories" in lib_text and "/audit?limit=120" in lib_text, "governance parity data misses memory or audit ledgers")
    require("/workers/status" in lib_text and "/workers/adapter-readiness" in lib_text, "agent-control parity data misses worker readiness")
    require("/security/production-readiness" in lib_text, "agent-control parity data misses production readiness")
    require("/workflows/customer-projects?limit=" in lib_text, "customer project index parity data is missing")
    require("/workflows/customer-delivery-board?limit=" in lib_text, "customer delivery board parity data is missing")
    require("/workflows/customer-projects/${encodeURIComponent(projectId)}/report" in lib_text, "customer project report parity data is missing")
    require("/approvals/${encodeURIComponent(id)}/${decision}" in lib_text, "approval decision parity action is missing")
    require("/memories/${encodeURIComponent(id)}/${decision}" in lib_text, "memory decision parity action is missing")
    require("/approvals/${encodeURIComponent(approvalId)}/${action}" in approvals_review_route_text, "approval review form fallback must write through MIS API")
    require("/memories/${encodeURIComponent(memoryId)}/${action}" in memory_review_route_text, "memory review form fallback must write through MIS API")
    require("/workflows/customer-projects/${encodeURIComponent(projectId)}/report-artifact" in report_archive_route_text, "customer report archive fallback must write through MIS API")
    require("/workspace/tasks" in app_frame_text and "/workspace/runs" in app_frame_text, "Next.js nav must expose task and run parity routes")
    require("/workspace/memory" in app_frame_text and "/workspace/audit" in app_frame_text, "Next.js nav must expose governance parity routes")
    require("/workspace/reports" in app_frame_text, "Next.js nav must expose reports parity route")
    require("/workspace/agents" in app_frame_text, "Next.js nav must expose agents parity route")
    require("loadAgentControlSnapshot" in agents_page_text and "Production security" in agents_page_text, "agents parity page must expose safety/readiness control plane")
    require("ReportsParityPage" in delivery_pages_text and "Customer delivery board" in delivery_pages_text, "reports parity page must expose delivery board")
    require("CustomerProjectReportParityPage" in delivery_pages_text and "Archive report" in delivery_pages_text, "customer report page must expose archive action")
    require("TasksParityPage" in ledger_pages_text and "RunsParityPage" in ledger_pages_text, "ledger parity pages are missing")
    require("ApprovalsParityPage" in ledger_pages_text and "decideApproval" in ledger_pages_text, "approval parity page must expose decision action")
    require('action="/workspace/approvals/review"' in ledger_pages_text, "approval parity page must keep the Next form fallback")
    require("MemoryParityPage" in governance_pages_text and "decideMemory" in governance_pages_text, "memory parity page must expose review action")
    require('action="/workspace/memory/review"' in governance_pages_text, "memory parity page must keep the Next form fallback")
    require("AuditParityPage" in governance_pages_text and "loadAudit" in governance_pages_text, "audit parity page must expose evidence readback")
    require("loadWorkspaceSnapshot" in dashboard_text, "workspace page must consume the shared Next.js MIS data contract")

    print(json.dumps({
        "ok": True,
        "next_app": str(NEXT_APP.relative_to(ROOT)),
        "routes": [
            "/workspace",
            "/workspace/agents",
            "/workspace/tasks",
            "/workspace/runs",
            "/workspace/approvals",
            "/workspace/memory",
            "/workspace/reports",
            "/workspace/customer-projects/[projectId]/report",
            "/workspace/audit",
            "/api/mis/[...path]",
        ],
        "stack": {
            "next": dependencies.get("next"),
            "react": dependencies.get("react"),
            "typescript": package.get("devDependencies", {}).get("typescript"),
        },
        "api_provider": "AGENTOPS_API_BASE or http://127.0.0.1:8765/api",
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
