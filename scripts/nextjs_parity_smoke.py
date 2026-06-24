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
        NEXT_APP / "app" / "workspace" / "agents" / "[agentId]" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "agents" / "dispatch-once" / "route.ts",
        NEXT_APP / "app" / "workspace" / "agents" / "release-task" / "route.ts",
        NEXT_APP / "app" / "workspace" / "agents" / "enrollment-request" / "route.ts",
        NEXT_APP / "app" / "workspace" / "agents" / "daemon-control" / "route.ts",
        NEXT_APP / "app" / "workspace" / "workers" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "commercial" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "governance" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "deployment" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "pixel-office" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "pixel-office" / "local-brief" / "route.ts",
        NEXT_APP / "app" / "workspace" / "dispatch" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "dispatch" / "template-run" / "route.ts",
        NEXT_APP / "app" / "workspace" / "dispatch" / "customer-task" / "route.ts",
        NEXT_APP / "app" / "workspace" / "dispatch" / "template-job" / "route.ts",
        NEXT_APP / "app" / "workspace" / "dispatch" / "customer-worker" / "route.ts",
        NEXT_APP / "app" / "workspace" / "dispatch" / "customer-worker-job" / "route.ts",
        NEXT_APP / "app" / "workspace" / "evidence" / "[manifestId]" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "tasks" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "tasks" / "[taskId]" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "runs" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "runs" / "[runId]" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "tool-calls" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "evaluations" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "connectors" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "connectors" / "trust" / "route.ts",
        NEXT_APP / "app" / "workspace" / "external-bases" / "notion" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "external-bases" / "notion" / "export" / "route.ts",
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
        NEXT_APP / "src" / "components" / "WorkerConsolePage.tsx",
        NEXT_APP / "src" / "components" / "AgentDetailPage.tsx",
        NEXT_APP / "src" / "components" / "CommercialPage.tsx",
        NEXT_APP / "src" / "components" / "GovernancePage.tsx",
        NEXT_APP / "src" / "components" / "DeploymentPage.tsx",
        NEXT_APP / "src" / "components" / "PixelOfficePage.tsx",
        NEXT_APP / "src" / "components" / "DispatchPage.tsx",
        NEXT_APP / "src" / "components" / "EvidencePage.tsx",
        NEXT_APP / "src" / "components" / "LedgerDetailPages.tsx",
        NEXT_APP / "src" / "components" / "DeliveryPages.tsx",
        NEXT_APP / "src" / "components" / "LedgerPages.tsx",
        NEXT_APP / "src" / "components" / "ToolCallPages.tsx",
        NEXT_APP / "src" / "components" / "EvaluationPages.tsx",
        NEXT_APP / "src" / "components" / "ConnectorPages.tsx",
        NEXT_APP / "src" / "components" / "NotionBasePage.tsx",
        NEXT_APP / "src" / "components" / "GovernancePages.tsx",
        NEXT_APP / "src" / "components" / "WorkspaceDashboard.tsx",
        NEXT_APP / "src" / "lib" / "mis.ts",
        NEXT_APP / "src" / "lib" / "misServer.ts",
        NEXT_APP / "src" / "styles" / "globals.css",
        ROOT / "scripts" / "ui_task_run_route_parity_smoke.py",
        ROOT / "scripts" / "ui_legacy_route_alias_smoke.py",
        ROOT / "scripts" / "ui_navigation_inventory_smoke.py",
        ROOT / "scripts" / "ui_route_retirement_packet_smoke.py",
        ROOT / "scripts" / "nextjs_agent_gateway_task_proxy_smoke.py",
        ROOT / "scripts" / "nextjs_agent_gateway_cli_worker_dogfood_smoke.py",
        ROOT / "scripts" / "nextjs_worker_dispatch_once_smoke.py",
        ROOT / "scripts" / "nextjs_pixel_office_floor_smoke.py",
        ROOT / "scripts" / "nextjs_pixel_office_dispatch_smoke.py",
        ROOT / "scripts" / "pixel_office_dispatch_retirement_evidence_smoke.py",
        ROOT / "scripts" / "local_brief_prepared_action_smoke.py",
        ROOT / "scripts" / "nextjs_local_brief_smoke.py",
        ROOT / "scripts" / "nextjs_customer_worker_dispatch_smoke.py",
        ROOT / "scripts" / "nextjs_customer_worker_async_job_smoke.py",
        ROOT / "scripts" / "nextjs_customer_worker_prepared_action_smoke.py",
        ROOT / "scripts" / "nextjs_worker_stuck_release_smoke.py",
        ROOT / "scripts" / "nextjs_enrollment_request_smoke.py",
        ROOT / "scripts" / "nextjs_worker_gateway_lifecycle_guard_smoke.py",
        ROOT / "scripts" / "nextjs_worker_daemon_control_smoke.py",
        ROOT / "scripts" / "nextjs_worker_console_parity_smoke.py",
        ROOT / "scripts" / "audit_retention_policy_smoke.py",
        ROOT / "scripts" / "audit_retention_controls_smoke.py",
        ROOT / "docs" / "UI_NAVIGATION_INVENTORY.json",
        ROOT / "docs" / "UI_ROUTE_RETIREMENT_PACKET.json",
        ROOT / "docs" / "PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json",
        ROOT / "docs" / "PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.md",
    ]

    for path in required_files:
        require(path.exists(), f"missing Next.js parity file: {path.relative_to(ROOT)}")

    route_text = read_text(NEXT_APP / "app" / "api" / "mis" / "[...path]" / "route.ts")
    approvals_review_route_text = read_text(NEXT_APP / "app" / "workspace" / "approvals" / "review" / "route.ts")
    memory_review_route_text = read_text(NEXT_APP / "app" / "workspace" / "memory" / "review" / "route.ts")
    report_archive_route_text = read_text(NEXT_APP / "app" / "workspace" / "customer-projects" / "[projectId]" / "report" / "archive" / "route.ts")
    dispatch_route_text = read_text(NEXT_APP / "app" / "workspace" / "dispatch" / "template-run" / "route.ts")
    customer_task_route_text = read_text(NEXT_APP / "app" / "workspace" / "dispatch" / "customer-task" / "route.ts")
    template_job_route_text = read_text(NEXT_APP / "app" / "workspace" / "dispatch" / "template-job" / "route.ts")
    customer_worker_dispatch_route_text = read_text(NEXT_APP / "app" / "workspace" / "dispatch" / "customer-worker" / "route.ts")
    customer_worker_job_route_text = read_text(NEXT_APP / "app" / "workspace" / "dispatch" / "customer-worker-job" / "route.ts")
    local_brief_route_text = read_text(NEXT_APP / "app" / "workspace" / "pixel-office" / "local-brief" / "route.ts")
    connector_trust_route_text = read_text(NEXT_APP / "app" / "workspace" / "connectors" / "trust" / "route.ts")
    notion_export_route_text = read_text(NEXT_APP / "app" / "workspace" / "external-bases" / "notion" / "export" / "route.ts")
    agents_dispatch_route_text = read_text(NEXT_APP / "app" / "workspace" / "agents" / "dispatch-once" / "route.ts")
    agents_release_route_text = read_text(NEXT_APP / "app" / "workspace" / "agents" / "release-task" / "route.ts")
    agents_enrollment_route_text = read_text(NEXT_APP / "app" / "workspace" / "agents" / "enrollment-request" / "route.ts")
    agents_daemon_route_text = read_text(NEXT_APP / "app" / "workspace" / "agents" / "daemon-control" / "route.ts")
    admin_task_alias_text = read_text(NEXT_APP / "app" / "admin" / "tasks" / "[taskId]" / "page.tsx")
    admin_runs_alias_text = read_text(NEXT_APP / "app" / "admin" / "runs" / "page.tsx")
    admin_run_alias_text = read_text(NEXT_APP / "app" / "admin" / "runs" / "[runId]" / "page.tsx")
    app_frame_text = read_text(NEXT_APP / "src" / "components" / "AppFrame.tsx")
    agents_page_text = read_text(NEXT_APP / "src" / "components" / "AgentsParityPage.tsx")
    worker_console_page_text = read_text(NEXT_APP / "src" / "components" / "WorkerConsolePage.tsx")
    agent_detail_page_text = read_text(NEXT_APP / "src" / "components" / "AgentDetailPage.tsx")
    commercial_page_text = read_text(NEXT_APP / "src" / "components" / "CommercialPage.tsx")
    governance_page_text = read_text(NEXT_APP / "src" / "components" / "GovernancePage.tsx")
    deployment_page_text = read_text(NEXT_APP / "src" / "components" / "DeploymentPage.tsx")
    pixel_office_page_text = read_text(NEXT_APP / "src" / "components" / "PixelOfficePage.tsx")
    dispatch_page_text = read_text(NEXT_APP / "src" / "components" / "DispatchPage.tsx")
    evidence_page_text = read_text(NEXT_APP / "src" / "components" / "EvidencePage.tsx")
    ledger_detail_pages_text = read_text(NEXT_APP / "src" / "components" / "LedgerDetailPages.tsx")
    delivery_pages_text = read_text(NEXT_APP / "src" / "components" / "DeliveryPages.tsx")
    ledger_pages_text = read_text(NEXT_APP / "src" / "components" / "LedgerPages.tsx")
    tool_call_pages_text = read_text(NEXT_APP / "src" / "components" / "ToolCallPages.tsx")
    evaluation_pages_text = read_text(NEXT_APP / "src" / "components" / "EvaluationPages.tsx")
    connector_pages_text = read_text(NEXT_APP / "src" / "components" / "ConnectorPages.tsx")
    notion_base_page_text = read_text(NEXT_APP / "src" / "components" / "NotionBasePage.tsx")
    governance_pages_text = read_text(NEXT_APP / "src" / "components" / "GovernancePages.tsx")
    dashboard_text = read_text(NEXT_APP / "src" / "components" / "WorkspaceDashboard.tsx")
    globals_text = read_text(NEXT_APP / "src" / "styles" / "globals.css")
    lib_text = read_text(NEXT_APP / "src" / "lib" / "mis.ts")
    server_lib_text = read_text(NEXT_APP / "src" / "lib" / "misServer.ts")
    playwright_smoke_text = read_text(ROOT / "scripts" / "nextjs_playwright_snapshot_smoke.py")
    gateway_task_proxy_smoke_text = read_text(ROOT / "scripts" / "nextjs_agent_gateway_task_proxy_smoke.py")
    gateway_cli_worker_dogfood_smoke_text = read_text(ROOT / "scripts" / "nextjs_agent_gateway_cli_worker_dogfood_smoke.py")
    worker_dispatch_smoke_text = read_text(ROOT / "scripts" / "nextjs_worker_dispatch_once_smoke.py")
    pixel_office_floor_smoke_text = read_text(ROOT / "scripts" / "nextjs_pixel_office_floor_smoke.py")
    pixel_office_dispatch_smoke_text = read_text(ROOT / "scripts" / "nextjs_pixel_office_dispatch_smoke.py")
    pixel_office_retirement_evidence_smoke_text = read_text(ROOT / "scripts" / "pixel_office_dispatch_retirement_evidence_smoke.py")
    pixel_office_retirement_evidence_text = read_text(ROOT / "docs" / "PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json")
    local_brief_prepared_action_smoke_text = read_text(ROOT / "scripts" / "local_brief_prepared_action_smoke.py")
    local_brief_smoke_text = read_text(ROOT / "scripts" / "nextjs_local_brief_smoke.py")
    customer_worker_dispatch_smoke_text = read_text(ROOT / "scripts" / "nextjs_customer_worker_dispatch_smoke.py")
    customer_worker_async_job_smoke_text = read_text(ROOT / "scripts" / "nextjs_customer_worker_async_job_smoke.py")
    customer_worker_prepared_action_smoke_text = read_text(ROOT / "scripts" / "nextjs_customer_worker_prepared_action_smoke.py")
    worker_release_smoke_text = read_text(ROOT / "scripts" / "nextjs_worker_stuck_release_smoke.py")
    enrollment_request_smoke_text = read_text(ROOT / "scripts" / "nextjs_enrollment_request_smoke.py")
    worker_gateway_lifecycle_smoke_text = read_text(ROOT / "scripts" / "nextjs_worker_gateway_lifecycle_guard_smoke.py")
    worker_daemon_smoke_text = read_text(ROOT / "scripts" / "nextjs_worker_daemon_control_smoke.py")
    worker_console_smoke_text = read_text(ROOT / "scripts" / "nextjs_worker_console_parity_smoke.py")
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
    require("mock_only_next_parity" in route_text and "isWorkerDispatchPath" in route_text, "API proxy must fail closed for non-mock worker dispatch")
    require("customerWorkerWorkflowGuard" in route_text and "isCustomerWorkerWorkflowPath" in route_text and "prepared_action_required" in route_text, "API proxy must route customer-worker live requests to prepared-action gates")
    require("prepared_action_required" in route_text and "isLocalBriefPath" in route_text, "API proxy must preserve local brief prepared-action routing")
    require("force_release_not_allowed_next_parity" in route_text and "isWorkerReleasePath" in route_text, "API proxy must fail closed for force worker task release")
    require("mock_daemon_only_next_parity" in route_text and "isWorkerDaemonPath" in route_text, "API proxy must fail closed for non-mock worker daemon controls")
    require("live_worker_daemon_not_allowed_next_parity" in route_text, "API proxy must fail closed for confirm/live worker daemon controls")
    require("enrollment_token_issue_not_allowed_next_parity" in route_text and "isEnrollmentTokenIssuePath" in route_text, "API proxy must fail closed for raw enrollment token issue routes")
    require("enrollmentRequestGuard" in route_text and "invalid_scopes" in route_text, "API proxy must validate enrollment request scopes before forwarding")
    require("nextjs_agent_gateway_task_proxy_v1" in gateway_task_proxy_smoke_text, "Next Agent Gateway task proxy smoke contract is missing")
    require("/api/mis/agent-gateway/tasks" in gateway_task_proxy_smoke_text, "Next Gateway task proxy smoke must exercise the Next /api/mis route")
    require("AGENTOPS_API_KEY" in gateway_task_proxy_smoke_text and "no_token_status == 401" in gateway_task_proxy_smoke_text, "Next Gateway task proxy smoke must disable local no-token fallback")
    require("direct_api_matches_next_proxy" in gateway_task_proxy_smoke_text, "Next Gateway task proxy smoke must compare direct MIS and Next proxy readback")
    require("nextjs_agent_gateway_cli_worker_dogfood_v1" in gateway_cli_worker_dogfood_smoke_text, "Next CLI worker dogfood smoke contract is missing")
    require("/api/mis/agent-gateway/tasks" in gateway_cli_worker_dogfood_smoke_text, "Next CLI worker dogfood must create the task through the Next proxy")
    require("scripts/agent_worker.py --once --adapter mock" in gateway_cli_worker_dogfood_smoke_text, "Next CLI worker dogfood must execute through the worker CLI entrypoint")
    require("/api/mis/runs/:run_id" in gateway_cli_worker_dogfood_smoke_text and "plan-evidence-manifests/:id/verify" in gateway_cli_worker_dogfood_smoke_text, "Next CLI worker dogfood must read evidence back through the Next proxy")
    require("nextjs_worker_dispatch_once_v1" in worker_dispatch_smoke_text, "Next worker dispatch once smoke contract is missing")
    require("/api/mis/workers/local/dispatch-once" in worker_dispatch_smoke_text, "Next worker dispatch smoke must exercise the /api/mis proxy route")
    require("/workspace/agents/dispatch-once" in worker_dispatch_smoke_text, "Next worker dispatch smoke must exercise the form fallback route")
    require("AGENTOPS_BASE_URL" in worker_dispatch_smoke_text, "Next worker dispatch smoke must isolate the worker subprocess base URL")
    require("non_mock_proxy_status" in worker_dispatch_smoke_text and "mock_only_next_parity" in worker_dispatch_smoke_text, "Next worker dispatch smoke must prove non-mock proxy and form dispatch fail closed")
    require("nextjs_pixel_office_floor_v1" in pixel_office_floor_smoke_text, "Next Pixel Office floor smoke contract is missing")
    require("/workspace/pixel-office" in pixel_office_floor_smoke_text, "Next Pixel Office smoke must exercise the App Router page")
    require("commercial-safe geometry" in pixel_office_floor_smoke_text and "live runtime disabled" in pixel_office_floor_smoke_text, "Next Pixel Office smoke must prove read-only safe map evidence")
    require("nextjs_pixel_office_dispatch_v1" in pixel_office_dispatch_smoke_text, "Next Pixel Office owner dispatch smoke contract is missing")
    require("/workspace/dispatch/customer-task" in pixel_office_dispatch_smoke_text and "/workspace/dispatch/template-job" in pixel_office_dispatch_smoke_text, "Next Pixel Office dispatch smoke must exercise owner task and template job form fallbacks")
    require("pixel_office_dispatch_retirement_evidence_v1" in pixel_office_retirement_evidence_smoke_text, "Pixel Office retirement evidence smoke contract is missing")
    require('"retirement_action": "not_executed"' in pixel_office_retirement_evidence_text and '"retirement_allowed": false' in pixel_office_retirement_evidence_text, "Pixel Office retirement evidence must stay fail-closed")
    require("/workspace/pixel-office" in pixel_office_retirement_evidence_text and "/workspace/dispatch" in pixel_office_retirement_evidence_text, "Pixel Office retirement evidence must name Vite and Next route pair")
    require("Owner dispatch workflow" in pixel_office_page_text and "owner-dispatch-workflow" in pixel_office_page_text, "Pixel Office page must expose the owner dispatch workflow bridge")
    require("template intake /workspace/dispatch" in pixel_office_floor_smoke_text and "delivery reports /workspace/reports" in pixel_office_floor_smoke_text, "Next Pixel Office smoke must prove owner dispatch workflow route bridge")
    require("nextjs_local_brief_v1" in local_brief_smoke_text, "Next local brief smoke contract is missing")
    require("/api/mis/workflows/local-brief" in local_brief_smoke_text, "Next local brief smoke must exercise the /api/mis proxy route")
    require("/workspace/pixel-office/local-brief" in local_brief_smoke_text, "Next local brief smoke must exercise the form fallback route")
    require("prepared_action_exact_resume" in local_brief_smoke_text and "approval_required" in local_brief_smoke_text and "prepared_action_already_consumed" in local_brief_smoke_text, "Next local brief smoke must prove prepared-action exact resume")
    require("local_brief_prepared_action_v1" in local_brief_prepared_action_smoke_text, "Local brief backend prepared-action smoke contract is missing")
    require("prepared_action_prompt_hash_mismatch" in local_brief_prepared_action_smoke_text, "Local brief backend smoke must prove hash mismatch blocking")
    require("nextjs_customer_worker_dispatch_v1" in customer_worker_dispatch_smoke_text, "Next customer-worker dispatch smoke contract is missing")
    require("/api/mis/workflows/customer-worker-task" in customer_worker_dispatch_smoke_text, "Next customer-worker dispatch smoke must exercise the /api/mis workflow proxy route")
    require("/workspace/dispatch/customer-worker" in customer_worker_dispatch_smoke_text, "Next customer-worker dispatch smoke must exercise the dispatch form fallback route")
    require("adapter_invalid" in customer_worker_dispatch_smoke_text, "Next customer-worker dispatch smoke must prove invalid adapters fail closed")
    require("waiting_approval" in customer_worker_dispatch_smoke_text and "plan-evidence-manifests/:id/verify" in customer_worker_dispatch_smoke_text, "Next customer-worker dispatch smoke must verify delivery approval and plan evidence readback")
    require("nextjs_customer_worker_async_job_v1" in customer_worker_async_job_smoke_text, "Next customer-worker async job smoke contract is missing")
    require("/api/mis/workflows/customer-worker-task/submit" in customer_worker_async_job_smoke_text, "Next customer-worker async smoke must exercise the /api/mis submit proxy route")
    require("/workspace/dispatch/customer-worker-job" in customer_worker_async_job_smoke_text, "Next customer-worker async smoke must exercise the async form fallback route")
    require("/api/mis/workflows/jobs/:job_id" in customer_worker_async_job_smoke_text, "Next customer-worker async smoke must read job status through the Next proxy")
    require("adapter_invalid" in customer_worker_async_job_smoke_text, "Next customer-worker async smoke must prove invalid async submit fails closed")
    require("nextjs_customer_worker_prepared_action_v1" in customer_worker_prepared_action_smoke_text, "Next customer-worker prepared-action smoke contract is missing")
    require("prepared_action_request_hash_mismatch" in customer_worker_prepared_action_smoke_text and "prepared_action_already_consumed" in customer_worker_prepared_action_smoke_text, "Next customer-worker prepared-action smoke must prove hash mismatch and replay blocking")
    require("/api/mis/workflows/customer-worker-prepared-actions" in customer_worker_prepared_action_smoke_text and "resume_form" in customer_worker_prepared_action_smoke_text, "Next customer-worker prepared-action smoke must prove ledger-derived safe resume readback")
    require("CustomerWorkerPreparedActionListPayload" in lib_text and "resume_form" in lib_text, "Next MIS types must include customer-worker prepared-action readback")
    require("/workflows/customer-task" in customer_task_route_text and "selected_agent_ids" in customer_task_route_text, "Customer task form route must forward owner task payload and selected team")
    require("/workflows/customer-task-templates/submit" in template_job_route_text and "template_job_status" in template_job_route_text, "Template async job form route must submit through the MIS workflow job API")
    require("Owner task composer" in dispatch_page_text and "/workspace/dispatch/customer-task" in dispatch_page_text and "/workspace/dispatch/template-job" in dispatch_page_text, "Dispatch page must expose owner dry-run/confirm and template async job controls")
    require("loadServerAgents" in read_text(NEXT_APP / "app" / "workspace" / "dispatch" / "page.tsx"), "Dispatch page must load agents for owner team selection")
    require("Prepared worker actions" in dispatch_page_text and "customer-worker-prepared-actions" in dispatch_page_text, "Dispatch page must expose the ledger-derived prepared-action queue")
    require("Resume approved worker" in dispatch_page_text and "Resume approved job" in dispatch_page_text, "Dispatch page must expose prepared-action resume controls")
    require("prepared_action_id" in customer_worker_dispatch_route_text and "request_hash" in customer_worker_dispatch_route_text and "selected_agent_ids" in customer_worker_dispatch_route_text and "template_id" in customer_worker_dispatch_route_text, "Customer-worker form route must preserve prepared-action resume ids plus owner/team/template payload")
    require("prepared_action_id" in customer_worker_job_route_text and "request_hash" in customer_worker_job_route_text and "selected_agent_ids" in customer_worker_job_route_text and "template_id" in customer_worker_job_route_text, "Customer-worker async form route must preserve prepared-action resume ids plus owner/team/template payload")
    require("nextjs_worker_stuck_release_v1" in worker_release_smoke_text, "Next worker stuck release smoke contract is missing")
    require("/api/mis/workers/tasks/release" in worker_release_smoke_text, "Next worker stuck release smoke must exercise the /api/mis release route")
    require("/workspace/agents/release-task" in worker_release_smoke_text, "Next worker stuck release smoke must exercise the release form fallback")
    require("force_release_not_allowed_next_parity" in worker_release_smoke_text, "Next worker stuck release smoke must prove force release fails closed")
    require("nextjs_enrollment_request_v1" in enrollment_request_smoke_text, "Next enrollment request smoke contract is missing")
    require("/api/mis/agent-gateway/enrollment/policy-preview" in enrollment_request_smoke_text, "Next enrollment smoke must exercise policy preview through /api/mis")
    require("/api/mis/agent-gateway/enrollment/request" in enrollment_request_smoke_text, "Next enrollment smoke must exercise approval-gated request through /api/mis")
    require("/workspace/agents/enrollment-request" in enrollment_request_smoke_text, "Next enrollment smoke must exercise the form fallback")
    require("enrollment_token_issue_not_allowed_next_parity" in enrollment_request_smoke_text, "Next enrollment smoke must prove raw token issue routes fail closed")
    require("invalid_scopes" in enrollment_request_smoke_text, "Next enrollment smoke must prove invalid scopes fail closed before backend filtering")
    require("nextjs_worker_gateway_lifecycle_guard_v1" in worker_gateway_lifecycle_smoke_text, "Next worker gateway lifecycle guard smoke contract is missing")
    require("/api/mis/agent-gateway/session/create" in worker_gateway_lifecycle_smoke_text and "/api/mis/agent-gateway/session/revoke" in worker_gateway_lifecycle_smoke_text, "Next lifecycle guard smoke must exercise session create/revoke blocks")
    require("/api/mis/agent-gateway/enrollment/revoke" in worker_gateway_lifecycle_smoke_text and "/api/mis/agent-gateway/enrollment/rotate" in worker_gateway_lifecycle_smoke_text, "Next lifecycle guard smoke must exercise enrollment revoke/rotate blocks")
    require("gateway_lifecycle_write_not_allowed_next_parity" in worker_gateway_lifecycle_smoke_text and "session_token" in worker_gateway_lifecycle_smoke_text, "Next lifecycle guard smoke must prove lifecycle writes fail closed before token/session leakage")
    require("nextjs_worker_daemon_control_v1" in worker_daemon_smoke_text, "Next worker daemon control smoke contract is missing")
    require("/api/mis/workers/local/start" in worker_daemon_smoke_text and "/api/mis/workers/local/restart" in worker_daemon_smoke_text and "/api/mis/workers/local/stop" in worker_daemon_smoke_text, "Next worker daemon smoke must exercise start/restart/stop proxy routes")
    require("/workspace/agents/daemon-control" in worker_daemon_smoke_text, "Next worker daemon smoke must exercise the form fallback route")
    require("mock_daemon_only_next_parity" in worker_daemon_smoke_text and "live_worker_daemon_not_allowed_next_parity" in worker_daemon_smoke_text, "Next worker daemon smoke must prove live daemon controls fail closed")
    require("Workers" in app_frame_text and "/workspace/workers" in app_frame_text, "Next navigation must expose the focused Worker Console route")
    require("WorkerConsolePage" in read_text(NEXT_APP / "app" / "workspace" / "workers" / "page.tsx"), "Worker route must render the Worker Console page")
    require("Worker Console" in worker_console_page_text and "worker-console-route" in worker_console_page_text, "Worker Console route marker is missing")
    require("worker-console-read-model" in worker_console_page_text and "worker_console_read_model_parity" in worker_console_page_text, "Worker Console must expose read-model parity proof")
    require("worker-console-live-boundary" in worker_console_page_text and "live daemon blocked" in worker_console_page_text and "direct token issue blocked" in worker_console_page_text, "Worker Console must expose live lifecycle fail-closed proof")
    require("worker-console-fleet-lanes" in worker_console_page_text and "Worker fleet lanes" in worker_console_page_text and "/workers/fleet" in worker_console_page_text, "Worker Console must expose fleet lane readback")
    require("worker-console-hygiene-plan" in worker_console_page_text and "Fleet hygiene plan" in worker_console_page_text and "/workers/fleet/hygiene" in worker_console_page_text, "Worker Console must expose read-only hygiene plan")
    require("worker-console-session-hygiene" in worker_console_page_text and "session token omitted" in worker_console_page_text and "session id hidden" in worker_console_page_text, "Worker Console must expose session hygiene without raw ids")
    require("worker-adapter-readiness-proof" in worker_console_page_text and "Adapter readiness" in worker_console_page_text, "Worker Console must expose adapter readiness proof")
    require("execution-mode endpoint pending" in worker_console_page_text, "Worker Console must not pretend execution-mode parity exists on this branch")
    require("nextjs_worker_console_parity_v1" in worker_console_smoke_text, "Next Worker Console parity smoke contract is missing")
    require("/workspace/workers" in worker_console_smoke_text and "/api/mis/workers/fleet" in worker_console_smoke_text and "/api/mis/workers/fleet/hygiene" in worker_console_smoke_text, "Next Worker Console smoke must exercise route plus fleet/hygiene APIs")
    require("mock_daemon_only_next_parity" in worker_console_smoke_text and "gateway_lifecycle_write_not_allowed_next_parity" in worker_console_smoke_text, "Next Worker Console smoke must prove lifecycle writes fail closed")
    require("AGENTOPS_API_BASE" in server_lib_text and "loadServerApprovals" in server_lib_text, "server-side first paint loaders are missing")
    require("/dashboard/metrics" in lib_text, "workspace parity data must include dashboard metrics")
    require("/tasks" in lib_text and "/runs" in lib_text and "/approvals" in lib_text, "workspace parity data misses core ledgers")
    require("/tool-calls" in lib_text and "loadToolCalls" in lib_text, "tool call ledger parity data is missing")
    require("/evaluations" in lib_text and "loadEvaluations" in lib_text, "evaluation ledger parity data is missing")
    require("/runtime-connectors" in lib_text and "loadRuntimeConnectors" in lib_text, "runtime connector parity data is missing")
    require("updateRuntimeConnectorTrust" in lib_text, "runtime connector trust parity action is missing")
    require("/integrations/notion/status" in lib_text and "loadNotionPreview" in lib_text, "Notion external base parity data is missing")
    require("/integrations/notion/dry-run-export" in lib_text and "/integrations/notion/export-confirmed" in lib_text, "Notion external base export actions are missing")
    require("/memories" in lib_text and "/audit?limit=120" in lib_text, "governance parity data misses memory or audit ledgers")
    require("/workers/status" in lib_text and "/workers/adapter-readiness" in lib_text, "agent-control parity data misses worker readiness")
    require("/workers/fleet" in lib_text and "loadWorkerFleet" in lib_text, "agent-control parity data misses worker fleet readback")
    require("/workers/fleet/hygiene" in lib_text and "loadWorkerFleetHygiene" in lib_text, "agent-control parity data misses worker fleet hygiene readback")
    require("loadServerWorkerFleet" in server_lib_text and "/workers/fleet" in server_lib_text, "server-side Worker Console loaders must include fleet readback")
    require("loadServerWorkerFleetHygiene" in server_lib_text and "/workers/fleet/hygiene" in server_lib_text, "server-side Worker Console loaders must include hygiene readback")
    require("loadServerWorkerAdapterReadiness" in server_lib_text and "/workers/adapter-readiness" in server_lib_text, "server-side Worker Console loaders must include adapter readiness")
    require("safeGatewaySessionsPayload" in server_lib_text and "parent_token_id_omitted" in server_lib_text, "server-side session loader must safe-project gateway sessions")
    require("/agent-gateway/enrollments" in lib_text and "loadAgentGatewayEnrollments" in lib_text, "agent-control parity data misses enrollment readback")
    require("/agent-gateway/sessions" in lib_text and "loadAgentGatewaySessions" in lib_text, "agent-control parity data misses session hygiene readback")
    require("/agent-gateway/enrollment/policy-preview" in lib_text and "previewAgentGatewayEnrollmentPolicy" in lib_text, "agent-control parity data misses enrollment policy preview")
    require("/agent-gateway/enrollment/request" in lib_text and "requestAgentGatewayEnrollment" in lib_text, "agent-control parity data misses approval-gated enrollment request")
    require("/workers/local/dispatch-once" in lib_text and "dispatchLocalWorkerOnce" in lib_text, "agent-control parity data misses worker dispatch mutation")
    require("/workers/tasks/release" in lib_text and "releaseWorkerTask" in lib_text, "agent-control parity data misses worker stuck release mutation")
    require("/workers/local/start" in lib_text and "startMockWorkerDaemon" in lib_text, "agent-control parity data misses mock worker daemon start")
    require("/workers/local/stop" in lib_text and "stopMockWorkerDaemon" in lib_text, "agent-control parity data misses mock worker daemon stop")
    require("/workers/local/restart" in lib_text and "restartMockWorkerDaemon" in lib_text, "agent-control parity data misses mock worker daemon restart")
    require("mock_only_next_parity" in lib_text, "agent-control parity mutation helper must fail closed outside mock")
    require("/agents/${encodeURIComponent(agentId)}/performance" in lib_text and "loadAgentPerformance" in lib_text, "agent detail performance parity data is missing")
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
    require("/workflows/customer-worker-task" in customer_worker_dispatch_route_text and "prepared_action_id" in customer_worker_dispatch_route_text and "request_hash" in customer_worker_dispatch_route_text, "customer-worker dispatch fallback must preserve prepared-action controls")
    require("/workflows/customer-worker-task/submit" in customer_worker_job_route_text and "prepared_action_id" in customer_worker_job_route_text and "request_hash" in customer_worker_job_route_text, "customer-worker async fallback must preserve prepared-action controls")
    require("/workflows/local-brief" in local_brief_route_text and "prepared_action_id" in local_brief_route_text and "approval_required" in local_brief_route_text, "local brief form fallback must preserve prepared-action controls")
    require("Customer worker dispatch" in dispatch_page_text and "/workspace/dispatch/customer-worker" in dispatch_page_text, "dispatch parity page must expose customer-worker dispatch form")
    require("Async worker jobs" in dispatch_page_text and "/workspace/dispatch/customer-worker-job" in dispatch_page_text, "dispatch parity page must expose async customer-worker job form")
    require("/workflows/jobs?limit=" in server_lib_text and "loadServerWorkflowJobs" in server_lib_text, "server-side dispatch loaders must include workflow job readback")
    require("/workflows/customer-worker-prepared-actions?limit=" in server_lib_text and "loadServerCustomerWorkerPreparedActions" in server_lib_text, "server-side dispatch loaders must include prepared-action readback")
    require("/runtime-connectors/${encodeURIComponent(connectorId)}/trust" in connector_trust_route_text, "connector trust form fallback must write through MIS API")
    require("/integrations/notion/export-confirmed" in notion_export_route_text and "/integrations/notion/dry-run-export" in notion_export_route_text, "Notion export form fallback must write through MIS API")
    require("/workspace/tasks" in app_frame_text and "/workspace/runs" in app_frame_text, "Next.js nav must expose task and run parity routes")
    require("/workspace/tool-calls" in app_frame_text, "Next.js nav must expose tool call ledger parity route")
    require("/workspace/evaluations" in app_frame_text, "Next.js nav must expose evaluation ledger parity route")
    require("/workspace/connectors" in app_frame_text, "Next.js nav must expose runtime connector parity route")
    require("/workspace/external-bases/notion" in app_frame_text, "Next.js nav must expose Notion external base parity route")
    require("/workspace/memory" in app_frame_text and "/workspace/audit" in app_frame_text, "Next.js nav must expose governance parity routes")
    require("/workspace/reports" in app_frame_text, "Next.js nav must expose reports parity route")
    require("/workspace/commercial" in app_frame_text, "Next.js nav must expose commercial parity route")
    require("/workspace/governance" in app_frame_text, "Next.js nav must expose governance control route")
    require("/workspace/deployment" in app_frame_text, "Next.js nav must expose deployment/BYOC route")
    require("/workspace/dispatch" in app_frame_text, "Next.js nav must expose dispatch parity route")
    require("/workspace/agents" in app_frame_text, "Next.js nav must expose agents parity route")
    require("loadAgentControlSnapshot" in agents_page_text and "Production security" in agents_page_text, "agents parity page must expose safety/readiness control plane")
    require("dispatchLocalWorkerOnce" in agents_page_text and "Run mock once" in agents_page_text, "agents parity page must expose safe mock worker dispatch")
    require('action="/workspace/agents/dispatch-once"' in agents_page_text, "agents parity page must keep the Next worker dispatch form fallback")
    require("mock_only_next_parity" in agents_dispatch_route_text and 'adapter !== "mock"' in agents_dispatch_route_text, "worker dispatch form fallback must reject non-mock adapters before upstream execution")
    require("releaseWorkerTask" in agents_page_text and "release-stuck-worker-task" in agents_page_text, "agents parity page must expose guarded stuck-task release")
    require('action="/workspace/agents/release-task"' in agents_page_text, "agents parity page must keep the Next worker release form fallback")
    require("/workers/tasks/release" in agents_release_route_text and "task_id_required" in agents_release_route_text, "worker release form fallback must write through MIS API with task id guard")
    require("startMockWorkerDaemon" in agents_page_text and "restartMockWorkerDaemon" in agents_page_text and "stopMockWorkerDaemon" in agents_page_text, "agents parity page must expose mock worker daemon controls")
    require('action="/workspace/agents/daemon-control"' in agents_page_text, "agents parity page must keep the Next worker daemon form fallback")
    require("mock-daemon-restart-form" in agents_page_text and "mock-daemon-stop-form" in agents_page_text, "agents parity page must keep restart/stop daemon form fallbacks")
    require("live daemon blocked" in agents_page_text and "mock-daemon-status" in agents_page_text, "agents parity page must show mock daemon status and live-daemon blocking")
    require("/workers/local/${action}" in agents_daemon_route_text and "mock_daemon_only_next_parity" in agents_daemon_route_text, "worker daemon form fallback must write through MIS API with mock-only guard")
    require("previewAgentGatewayEnrollmentPolicy" in agents_page_text and "requestAgentGatewayEnrollment" in agents_page_text, "agents parity page must expose approval-gated enrollment request")
    require('action="/workspace/agents/enrollment-request"' in agents_page_text, "agents parity page must keep the Next enrollment request form fallback")
    require("direct token issue blocked" in agents_page_text and "token omitted" in agents_page_text, "agents parity page must show enrollment token-safety state")
    require("agent-gateway-session-hygiene" in agents_page_text and "session token omitted" in agents_page_text and "session create blocked" in agents_page_text, "agents parity page must show Agent Gateway session hygiene state")
    require("session.session_ref" in agents_page_text and "session id hidden" in agents_page_text, "agents parity page must avoid rendering raw session ids")
    require("/agent-gateway/enrollment/request" in agents_enrollment_route_text and "invalid_scopes" in agents_enrollment_route_text, "enrollment request form fallback must validate scopes and write through approval-gated MIS API")
    require("isGatewayLifecycleWritePath" in route_text and "gateway_lifecycle_write_not_allowed_next_parity" in route_text, "Next MIS proxy must guard Agent Gateway lifecycle writes")
    require("agent-gateway/session/create" in route_text and "agent-gateway/session/revoke" in route_text and "agent-gateway/enrollment/revoke" in route_text, "Next MIS proxy must name blocked session/enrollment lifecycle routes")
    require("safeGatewaySessionsPayload" in route_text and "session_id_omitted" in route_text and "parent_token_id_omitted" in route_text, "Next MIS proxy must project safe session readback")
    require("/workspace/agents/${encodeURIComponent(agent.agent_id)}" in agents_page_text, "agents parity page must link rows to agent detail")
    require("AgentDetailParityPage" in agent_detail_page_text and "loadAgentPerformance" in agent_detail_page_text, "agent detail page must load live performance data")
    require("Per-agent performance" in agent_detail_page_text and "Recent Runs" in agent_detail_page_text, "agent detail page must expose performance and recent run evidence")
    require("/workspace/runs/${encodeURIComponent(run.run_id)}" in agent_detail_page_text, "agent detail page must link recent runs to run detail")
    require("/workspace/tasks/${encodeURIComponent(run.task_id)}" in agent_detail_page_text, "agent detail page must link recent runs to task detail")
    require("CommercialParityPage" in commercial_page_text and "Capability matrix" in commercial_page_text and "Fail-closed gates" in commercial_page_text, "commercial parity page must expose capability gates")
    require("billing call" in commercial_page_text and "token omitted" in commercial_page_text, "commercial parity page must expose safety proof")
    require("loadServerCommercialEntitlements" in server_lib_text, "commercial parity page must load server entitlement state")
    require("GovernanceParityPage" in governance_page_text and "Production readiness" in governance_page_text and "Session governance" in governance_page_text, "governance parity page must expose production/session governance")
    require("session id omitted" in governance_page_text and "Audit evidence" in governance_page_text, "governance parity page must avoid raw session ids and expose audit evidence")
    require("loadServerSecurityProductionReadiness" in server_lib_text and "loadServerGatewaySessions" in server_lib_text, "governance parity loaders are missing")
    require("DeploymentParityPage" in deployment_page_text and "Backup and restore evidence" in deployment_page_text and "Storage and retention" in deployment_page_text, "deployment parity page must expose BYOC evidence")
    require("Deployment readiness verdict" in deployment_page_text and "loadServerDeploymentReadiness" in server_lib_text, "deployment parity page must load deployment readiness verdict")
    require("/deployment/readiness" in server_lib_text and "DeploymentReadinessPayload" in lib_text, "deployment readiness loader/type is missing")
    require("/deployment/enterprise-controls" in server_lib_text and "EnterpriseControlsPayload" in lib_text, "enterprise controls loader/type is missing")
    require("raw rows printed false" in deployment_page_text and "Backup restore remains CLI-confirmed" in deployment_page_text, "deployment parity page must keep restore explicit and read-only")
    require("Recovery drill" in deployment_page_text and "Signed export" in deployment_page_text and "signed audit export requires a customer key" in deployment_page_text, "deployment parity page must expose recovery drill and signed audit export readiness")
    require("deployment_checks" in lib_text and "signed_audit_export_contract" in deployment_page_text and "signed_export_tamper_detection" in deployment_page_text, "deployment parity page must consume local deployment checks")
    require("Storage backend migration gate" in deployment_page_text and "writes allowed" in deployment_page_text and "fallback" in deployment_page_text, "deployment parity page must expose storage backend migration gates")
    require("PixelOfficeParityPage" in pixel_office_page_text and "Pixel Operating Map" in pixel_office_page_text, "pixel office parity page must render the operating map")
    require("commercial-safe geometry" in pixel_office_page_text and "no Star Office assets" in pixel_office_page_text and "live runtime disabled" in pixel_office_page_text, "pixel office parity page must expose asset and live-runtime boundaries")
    require("Local brief controls" in pixel_office_page_text and "/workspace/pixel-office/local-brief" in pixel_office_page_text and "live brief approval-gated" in pixel_office_page_text and "Resume approved brief" in pixel_office_page_text, "pixel office parity page must expose local brief prepared-action controls")
    require("loadServerDashboardMetrics" in server_lib_text and "loadServerAgents" in server_lib_text and "loadServerTasks" in server_lib_text and "loadServerRuns" in server_lib_text, "pixel office server loaders are missing")
    require("/workspace/pixel-office" in app_frame_text, "Next.js nav must expose Pixel Office parity route")
    require("audit_retention_policy_v1" in deployment_page_text and "delete performed" in deployment_page_text and "raw rows omitted" in deployment_page_text, "deployment parity page must expose read-only retention policy proof")
    require("/audit/retention-policy" in server_lib_text and "loadServerAuditRetentionPolicy" in server_lib_text, "deployment parity page must directly load audit retention policy")
    require("loadServerAuditRetentionPolicy" in read_text(NEXT_APP / "app" / "workspace" / "deployment" / "page.tsx"), "deployment page must request audit retention policy in parallel")
    require("audit_retention_policy_v1" in read_text(ROOT / "scripts" / "audit_retention_policy_smoke.py"), "audit retention policy smoke contract is missing")
    require("audit_retention_controls_v1" in deployment_page_text and "cleanup approval" in deployment_page_text and "legal hold check" in deployment_page_text, "deployment parity page must expose retention controls proof")
    require("active holds" in deployment_page_text and "unknown" in deployment_page_text, "deployment parity page must avoid claiming zero legal holds when registry is absent")
    require("/audit/retention-controls" in server_lib_text and "loadServerAuditRetentionControls" in server_lib_text, "deployment parity page must directly load audit retention controls")
    require("loadServerAuditRetentionControls" in read_text(NEXT_APP / "app" / "workspace" / "deployment" / "page.tsx"), "deployment page must request audit retention controls in parallel")
    require("audit_retention_controls_v1" in read_text(ROOT / "scripts" / "audit_retention_controls_smoke.py"), "audit retention controls smoke contract is missing")
    require("--configured-retention-fixture" in playwright_smoke_text and "nextjs_deployment_configured_retention_fixture_v1" in playwright_smoke_text, "browser smoke must expose a focused configured deployment retention fixture")
    require("verify_deployment_configured_retention" in playwright_smoke_text and "deployment_configured_retention_controls" in playwright_smoke_text, "browser smoke must verify configured deployment retention controls")
    require("AGENTOPS_RETENTION_CONTROLS_PATH" in playwright_smoke_text and "active_legal_holds" in playwright_smoke_text and "db_dump_hash" in playwright_smoke_text, "browser smoke must use an isolated retention-controls fixture and prove read-only behavior")
    require("dangerous_cleanup_parameter_rejected" in playwright_smoke_text and "retention-controls?cleanup=true" in playwright_smoke_text, "browser smoke must prove dangerous retention cleanup queries fail closed through the Next proxy")
    require("Raw Next deployment legal hold reason" in playwright_smoke_text and "Highly confidential Next deployment subject" in playwright_smoke_text, "browser smoke must seed raw legal-hold markers and assert omission")
    require("loadServerLocalReadiness" in server_lib_text and "loadServerStorageBackendStatus" in server_lib_text, "deployment parity loaders are missing")
    require("DispatchParityPage" in dispatch_page_text and "Entitlement required" in dispatch_page_text, "dispatch parity page must expose fail-closed entitlement state")
    require("verify_dispatch_entitlement_block" in playwright_smoke_text and "verify_dispatch_template_run_success" in playwright_smoke_text, "browser smoke must verify both blocked and entitled dispatch paths")
    require("AGENTOPS_ENTITLEMENTS_PATH" in playwright_smoke_text and "pro_workspace" in playwright_smoke_text, "browser smoke must use an isolated commercial entitlement fixture")
    require("AGENTOPS_BASE_URL" in playwright_smoke_text and "api_base" in playwright_smoke_text, "browser smoke must point nested local workflows at its isolated MIS API")
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
    require("EvaluationsParityPage" in evaluation_pages_text and "loadEvaluations" in evaluation_pages_text, "evaluation parity page must load the live evaluation ledger")
    require("/workspace/runs/${encodeURIComponent(evaluation.run_id)}" in evaluation_pages_text, "evaluation parity page must link evaluations to workspace run detail")
    require("/workspace/tasks/${encodeURIComponent(evaluation.task_id)}" in evaluation_pages_text, "evaluation parity page must link evaluations to workspace task detail")
    require("average score" in evaluation_pages_text and "failed gates" in evaluation_pages_text, "evaluation parity page must expose score and failed gate summaries")
    require("RuntimeConnectorsParityPage" in connector_pages_text and "loadRuntimeConnectors" in connector_pages_text, "runtime connector parity page must load live connectors")
    require("Runtime Trust Registry" in connector_pages_text and "allow real run" in connector_pages_text and "require confirm" in connector_pages_text, "runtime connector parity page must expose trust and confirmation gates")
    require('action="/workspace/connectors/trust"' in connector_pages_text, "runtime connector parity page must keep the Next form fallback")
    require("updateRuntimeConnectorTrust" in connector_pages_text and 'trustStatus === "blocked" ? "Block"' in connector_pages_text, "runtime connector parity page must expose trust update controls")
    require("NotionExternalBaseParityPage" in notion_base_page_text and "loadNotionPreview" in notion_base_page_text, "Notion external base page must load live preview data")
    require("notion_confirmed_export" in notion_base_page_text and "billing call false" in notion_base_page_text, "Notion external base page must expose fail-closed entitlement proof")
    require('action="/workspace/external-bases/notion/export"' in notion_base_page_text, "Notion external base page must keep the Next export form fallback")
    require("runNotionDryRunExport" in notion_base_page_text and "runNotionConfirmedExport" in notion_base_page_text, "Notion external base page must expose dry-run and confirmed export actions")
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
            "/workspace/agents/[agentId]",
            "/workspace/agents/dispatch-once",
            "/workspace/agents/release-task",
            "/workspace/agents/enrollment-request",
            "/workspace/agents/daemon-control",
            "/workspace/workers",
            "/workspace/commercial",
            "/workspace/governance",
            "/workspace/deployment",
            "/workspace/pixel-office",
            "/workspace/pixel-office/local-brief",
            "/workspace/dispatch",
            "/workspace/dispatch/customer-task",
            "/workspace/dispatch/template-job",
            "/workspace/dispatch/customer-worker",
            "/workspace/dispatch/customer-worker-job",
            "/workspace/evidence/[manifestId]",
            "/workspace/tasks",
            "/workspace/tasks/[taskId]",
            "/workspace/runs",
            "/workspace/runs/[runId]",
            "/workspace/tool-calls",
            "/workspace/evaluations",
            "/workspace/connectors",
            "/workspace/external-bases/notion",
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
        "contracts": [
            "nextjs_agent_gateway_task_proxy_v1",
            "nextjs_agent_gateway_cli_worker_dogfood_v1",
            "nextjs_worker_dispatch_once_v1",
            "nextjs_pixel_office_floor_v1",
            "nextjs_pixel_office_dispatch_v1",
            "pixel_office_dispatch_retirement_evidence_v1",
            "local_brief_prepared_action_v1",
            "nextjs_local_brief_v1",
            "nextjs_customer_worker_dispatch_v1",
            "nextjs_customer_worker_async_job_v1",
            "nextjs_customer_worker_prepared_action_v1",
            "nextjs_worker_stuck_release_v1",
            "nextjs_enrollment_request_v1",
            "nextjs_worker_gateway_lifecycle_guard_v1",
            "nextjs_worker_daemon_control_v1",
            "nextjs_worker_console_parity_v1",
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
