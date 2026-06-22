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
        NEXT_APP / "app" / "workspace" / "commercial" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "governance" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "deployment" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "dispatch" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "dispatch" / "template-run" / "route.ts",
        NEXT_APP / "app" / "workspace" / "evidence" / "[manifestId]" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "tasks" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "tasks" / "[taskId]" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "runs" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "runs" / "[runId]" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "tool-calls" / "page.tsx",
        NEXT_APP / "app" / "admin" / "tasks" / "[taskId]" / "page.tsx",
        NEXT_APP / "app" / "admin" / "runs" / "page.tsx",
        NEXT_APP / "app" / "admin" / "runs" / "[runId]" / "page.tsx",
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
        NEXT_APP / "src" / "components" / "CommercialPage.tsx",
        NEXT_APP / "src" / "components" / "GovernancePage.tsx",
        NEXT_APP / "src" / "components" / "DeploymentPage.tsx",
        NEXT_APP / "src" / "components" / "DispatchPage.tsx",
        NEXT_APP / "src" / "components" / "EvidencePage.tsx",
        NEXT_APP / "src" / "components" / "LedgerDetailPages.tsx",
        NEXT_APP / "src" / "components" / "DeliveryPages.tsx",
        NEXT_APP / "src" / "components" / "LedgerPages.tsx",
        NEXT_APP / "src" / "components" / "ToolCallPages.tsx",
        NEXT_APP / "src" / "components" / "GovernancePages.tsx",
        NEXT_APP / "src" / "components" / "WorkspaceDashboard.tsx",
        NEXT_APP / "src" / "lib" / "mis.ts",
        NEXT_APP / "src" / "lib" / "misServer.ts",
        NEXT_APP / "src" / "styles" / "globals.css",
        ROOT / "scripts" / "ui_task_run_route_parity_smoke.py",
        ROOT / "scripts" / "ui_legacy_route_alias_smoke.py",
        ROOT / "scripts" / "ui_navigation_inventory_smoke.py",
        ROOT / "scripts" / "ui_route_retirement_packet_smoke.py",
        ROOT / "docs" / "UI_NAVIGATION_INVENTORY.json",
        ROOT / "docs" / "UI_ROUTE_RETIREMENT_PACKET.json",
    ]

    for path in required_files:
        require(path.exists(), f"missing Next.js parity file: {path.relative_to(ROOT)}")

    route_text = read_text(NEXT_APP / "app" / "api" / "mis" / "[...path]" / "route.ts")
    approvals_review_route_text = read_text(NEXT_APP / "app" / "workspace" / "approvals" / "review" / "route.ts")
    memory_review_route_text = read_text(NEXT_APP / "app" / "workspace" / "memory" / "review" / "route.ts")
    report_archive_route_text = read_text(NEXT_APP / "app" / "workspace" / "customer-projects" / "[projectId]" / "report" / "archive" / "route.ts")
    dispatch_route_text = read_text(NEXT_APP / "app" / "workspace" / "dispatch" / "template-run" / "route.ts")
    admin_task_alias_text = read_text(NEXT_APP / "app" / "admin" / "tasks" / "[taskId]" / "page.tsx")
    admin_runs_alias_text = read_text(NEXT_APP / "app" / "admin" / "runs" / "page.tsx")
    admin_run_alias_text = read_text(NEXT_APP / "app" / "admin" / "runs" / "[runId]" / "page.tsx")
    app_frame_text = read_text(NEXT_APP / "src" / "components" / "AppFrame.tsx")
    agents_page_text = read_text(NEXT_APP / "src" / "components" / "AgentsParityPage.tsx")
    commercial_page_text = read_text(NEXT_APP / "src" / "components" / "CommercialPage.tsx")
    governance_page_text = read_text(NEXT_APP / "src" / "components" / "GovernancePage.tsx")
    deployment_page_text = read_text(NEXT_APP / "src" / "components" / "DeploymentPage.tsx")
    dispatch_page_text = read_text(NEXT_APP / "src" / "components" / "DispatchPage.tsx")
    evidence_page_text = read_text(NEXT_APP / "src" / "components" / "EvidencePage.tsx")
    ledger_detail_pages_text = read_text(NEXT_APP / "src" / "components" / "LedgerDetailPages.tsx")
    delivery_pages_text = read_text(NEXT_APP / "src" / "components" / "DeliveryPages.tsx")
    ledger_pages_text = read_text(NEXT_APP / "src" / "components" / "LedgerPages.tsx")
    tool_call_pages_text = read_text(NEXT_APP / "src" / "components" / "ToolCallPages.tsx")
    governance_pages_text = read_text(NEXT_APP / "src" / "components" / "GovernancePages.tsx")
    dashboard_text = read_text(NEXT_APP / "src" / "components" / "WorkspaceDashboard.tsx")
    globals_text = read_text(NEXT_APP / "src" / "styles" / "globals.css")
    lib_text = read_text(NEXT_APP / "src" / "lib" / "mis.ts")
    server_lib_text = read_text(NEXT_APP / "src" / "lib" / "misServer.ts")
    playwright_smoke_text = read_text(ROOT / "scripts" / "nextjs_playwright_snapshot_smoke.py")
    route_parity_smoke_text = read_text(ROOT / "scripts" / "ui_task_run_route_parity_smoke.py")
    route_alias_smoke_text = read_text(ROOT / "scripts" / "ui_legacy_route_alias_smoke.py")
    navigation_inventory_smoke_text = read_text(ROOT / "scripts" / "ui_navigation_inventory_smoke.py")
    navigation_inventory_text = read_text(ROOT / "docs" / "UI_NAVIGATION_INVENTORY.json")
    retirement_packet_smoke_text = read_text(ROOT / "scripts" / "ui_route_retirement_packet_smoke.py")
    retirement_packet_text = read_text(ROOT / "docs" / "UI_ROUTE_RETIREMENT_PACKET.json")

    require(dependencies.get("next") == "16.2.9", "Next.js version is not pinned to the selected migration version")
    require(dependencies.get("react") == "19.2.7", "React version is not pinned to the selected migration version")
    require("build" in scripts and "next build" in scripts["build"], "Next.js build script is missing")
    require("AGENTOPS_API_BASE" in route_text, "API proxy must be configurable with AGENTOPS_API_BASE")
    require("AGENTOPS_API_BASE" in server_lib_text and "loadServerApprovals" in server_lib_text, "server-side first paint loaders are missing")
    require("/dashboard/metrics" in lib_text, "workspace parity data must include dashboard metrics")
    require("/tasks" in lib_text and "/runs" in lib_text and "/approvals" in lib_text, "workspace parity data misses core ledgers")
    require("/tool-calls" in lib_text and "loadToolCalls" in lib_text, "tool call ledger parity data is missing")
    require("/memories" in lib_text and "/audit?limit=120" in lib_text, "governance parity data misses memory or audit ledgers")
    require("/workers/status" in lib_text and "/workers/adapter-readiness" in lib_text, "agent-control parity data misses worker readiness")
    require("/security/production-readiness" in lib_text, "agent-control parity data misses production readiness")
    require("/local/readiness" in server_lib_text, "deployment parity data misses local readiness")
    require("/agent-gateway/sessions" in server_lib_text, "governance parity data misses session readback")
    require("/workflows/customer-projects?limit=" in lib_text, "customer project index parity data is missing")
    require("/workflows/customer-delivery-board?limit=" in lib_text, "customer delivery board parity data is missing")
    require("/workflows/customer-projects/${encodeURIComponent(projectId)}/report" in lib_text, "customer project report parity data is missing")
    require("/commercial/entitlements" in lib_text, "commercial entitlement parity data is missing")
    require("/storage/backend-status" in lib_text and "/storage/backend-status" in server_lib_text, "storage backend parity data is missing")
    require("/workflows/customer-task-templates" in lib_text, "customer task template parity data is missing")
    require("/approvals/${encodeURIComponent(id)}/${decision}" in lib_text, "approval decision parity action is missing")
    require("/memories/${encodeURIComponent(id)}/${decision}" in lib_text, "memory decision parity action is missing")
    require("/approvals/${encodeURIComponent(approvalId)}/${action}" in approvals_review_route_text, "approval review form fallback must write through MIS API")
    require("/memories/${encodeURIComponent(memoryId)}/${action}" in memory_review_route_text, "memory review form fallback must write through MIS API")
    require("/workflows/customer-projects/${encodeURIComponent(projectId)}/report-artifact" in report_archive_route_text, "customer report archive fallback must write through MIS API")
    require("/workflows/customer-task-templates/run" in dispatch_route_text and "entitlement_required" in dispatch_route_text, "dispatch template fallback must preserve entitlement blocking")
    require("/workspace/tasks" in app_frame_text and "/workspace/runs" in app_frame_text, "Next.js nav must expose task and run parity routes")
    require("/workspace/tool-calls" in app_frame_text, "Next.js nav must expose tool call ledger parity route")
    require("/workspace/memory" in app_frame_text and "/workspace/audit" in app_frame_text, "Next.js nav must expose governance parity routes")
    require("/workspace/reports" in app_frame_text, "Next.js nav must expose reports parity route")
    require("/workspace/commercial" in app_frame_text, "Next.js nav must expose commercial parity route")
    require("/workspace/governance" in app_frame_text, "Next.js nav must expose governance control route")
    require("/workspace/deployment" in app_frame_text, "Next.js nav must expose deployment/BYOC route")
    require("/workspace/dispatch" in app_frame_text, "Next.js nav must expose dispatch parity route")
    require("/workspace/agents" in app_frame_text, "Next.js nav must expose agents parity route")
    require("loadAgentControlSnapshot" in agents_page_text and "Production security" in agents_page_text, "agents parity page must expose safety/readiness control plane")
    require("CommercialParityPage" in commercial_page_text and "Capability matrix" in commercial_page_text and "Fail-closed gates" in commercial_page_text, "commercial parity page must expose capability gates")
    require("billing call" in commercial_page_text and "token omitted" in commercial_page_text, "commercial parity page must expose safety proof")
    require("loadServerCommercialEntitlements" in server_lib_text, "commercial parity page must load server entitlement state")
    require("GovernanceParityPage" in governance_page_text and "Production readiness" in governance_page_text and "Session governance" in governance_page_text, "governance parity page must expose production/session governance")
    require("session id omitted" in governance_page_text and "Audit evidence" in governance_page_text, "governance parity page must avoid raw session ids and expose audit evidence")
    require("loadServerSecurityProductionReadiness" in server_lib_text and "loadServerGatewaySessions" in server_lib_text, "governance parity loaders are missing")
    require("DeploymentParityPage" in deployment_page_text and "Backup and restore evidence" in deployment_page_text and "Storage and retention" in deployment_page_text, "deployment parity page must expose BYOC evidence")
    require("raw rows printed false" in deployment_page_text and "Backup restore remains CLI-confirmed" in deployment_page_text, "deployment parity page must keep restore explicit and read-only")
    require("Storage backend migration gate" in deployment_page_text and "writes allowed" in deployment_page_text and "fallback" in deployment_page_text, "deployment parity page must expose storage backend migration gates")
    require("loadServerLocalReadiness" in server_lib_text and "loadServerStorageBackendStatus" in server_lib_text, "deployment parity loaders are missing")
    require("DispatchParityPage" in dispatch_page_text and "Entitlement required" in dispatch_page_text, "dispatch parity page must expose fail-closed entitlement state")
    require("verify_dispatch_entitlement_block" in playwright_smoke_text and "verify_dispatch_template_run_success" in playwright_smoke_text, "browser smoke must verify both blocked and entitled dispatch paths")
    require("AGENTOPS_ENTITLEMENTS_PATH" in playwright_smoke_text and "pro_workspace" in playwright_smoke_text, "browser smoke must use an isolated commercial entitlement fixture")
    require("ReportsParityPage" in delivery_pages_text and "Customer delivery board" in delivery_pages_text, "reports parity page must expose delivery board")
    require("CustomerProjectReportParityPage" in delivery_pages_text and "Archive report" in delivery_pages_text, "customer report page must expose archive action")
    require("Agent Plan evidence" in delivery_pages_text and "execution_evidence" in lib_text, "customer report page must expose Agent Plan evidence")
    require("/workspace/evidence/" in delivery_pages_text and "EvidenceDrilldownPage" in evidence_page_text, "customer report page must link to evidence drilldown")
    require("loadServerEvidenceDrilldown" in server_lib_text and "/agent-gateway/plan-evidence-manifests/" in server_lib_text, "evidence drilldown must load Agent Gateway read evidence")
    require("Manifest verification" in evidence_page_text and "Run graph" in evidence_page_text, "evidence drilldown must expose verification and run graph")
    require("/workspace/runs/" in evidence_page_text and "/workspace/tasks/" in evidence_page_text, "evidence drilldown must link to task/run detail")
    require("TaskDetailPage" in ledger_detail_pages_text and "RunDetailPage" in ledger_detail_pages_text, "task/run detail pages are missing")
    require("loadServerTaskDetail" in server_lib_text and "loadServerRunDetail" in server_lib_text, "task/run detail loaders are missing")
    require("TasksParityPage" in ledger_pages_text and "RunsParityPage" in ledger_pages_text, "ledger parity pages are missing")
    require("ToolCallsParityPage" in tool_call_pages_text and "loadToolCalls" in tool_call_pages_text, "tool call parity page must load the live tool-call ledger")
    require("/workspace/runs/${encodeURIComponent(toolCall.run_id)}" in tool_call_pages_text, "tool call parity page must link tool calls to workspace run detail")
    require("riskFilter" in tool_call_pages_text and "high-risk" in tool_call_pages_text, "tool call parity page must expose risk filtering and high-risk summary")
    require("/workspace/tasks/${encodeURIComponent(taskId)}" in admin_task_alias_text and "redirect(" in admin_task_alias_text, "legacy admin task detail must redirect to workspace task detail")
    require('redirect("/workspace/runs")' in admin_runs_alias_text, "legacy admin run ledger must redirect to workspace runs")
    require("/workspace/runs/${encodeURIComponent(runId)}" in admin_run_alias_text and "redirect(" in admin_run_alias_text, "legacy admin run detail must redirect to workspace run detail")
    require("ui_legacy_route_alias_v1" in route_alias_smoke_text, "legacy route alias smoke contract is missing")
    require("ui_navigation_inventory_v1" in navigation_inventory_smoke_text, "navigation inventory smoke contract is missing")
    require("redirect_alias_only" in navigation_inventory_text, "navigation inventory must keep legacy admin routes as aliases only")
    require("ui_route_retirement_packet_v1" in retirement_packet_smoke_text, "route retirement packet smoke contract is missing")
    require('"retirement_action": "not_executed"' in retirement_packet_text, "route retirement packet must not execute retirement")
    require("next/link" in ledger_pages_text, "task/run list parity pages must use Next links")
    require("/workspace/tasks/${encodeURIComponent(task.task_id)}" in ledger_pages_text, "task list rows must link to task detail")
    require("/workspace/runs/${encodeURIComponent(run.run_id)}" in ledger_pages_text, "run list rows must link to run detail")
    require("taskIdForLink = task?.task_id || run?.task_id" in ledger_detail_pages_text, "run detail must fall back to run.task_id for task links")
    require("/workspace/tasks/${encodeURIComponent(taskIdForLink)}" in ledger_detail_pages_text, "run detail must link back to task")
    require(".tableLink" in globals_text, "run list detail links must have stable table styling")
    require("ui_task_run_route_parity_v1" in route_parity_smoke_text, "task/run route parity smoke contract is missing")
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
            "/workspace/commercial",
            "/workspace/governance",
            "/workspace/deployment",
            "/workspace/dispatch",
            "/workspace/evidence/[manifestId]",
            "/workspace/tasks",
            "/workspace/tasks/[taskId]",
            "/workspace/runs",
            "/workspace/runs/[runId]",
            "/workspace/tool-calls",
            "/admin/tasks/[taskId]",
            "/admin/runs",
            "/admin/runs/[runId]",
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
