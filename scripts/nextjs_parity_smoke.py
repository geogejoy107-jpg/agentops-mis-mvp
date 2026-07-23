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
    overrides = package.get("overrides", {})
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
        NEXT_APP / "app" / "workspace" / "templates" / "page.tsx",
        NEXT_APP / "app" / "workspace" / "templates" / "migration-preview" / "route.ts",
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
        NEXT_APP / "app" / "api" / "mis" / "agent-gateway" / "register" / "route.ts",
        NEXT_APP / "app" / "api" / "mis" / "agent-gateway" / "heartbeat" / "route.ts",
        NEXT_APP / "app" / "api" / "mis" / "agent-gateway" / "audit" / "route.ts",
        NEXT_APP / "app" / "api" / "mis" / "agent-gateway" / "tasks" / "pull" / "route.ts",
        NEXT_APP / "app" / "api" / "mis" / "agent-gateway" / "tasks" / "[taskId]" / "claim" / "route.ts",
        NEXT_APP / "app" / "api" / "mis" / "tasks" / "route.ts",
        NEXT_APP / "app" / "api" / "mis" / "runs" / "route.ts",
        NEXT_APP / "app" / "api" / "mis" / "approvals" / "route.ts",
        NEXT_APP / "app" / "api" / "mis" / "audit" / "route.ts",
        NEXT_APP / "app" / "api" / "mis" / "dashboard" / "metrics" / "route.ts",
        NEXT_APP / "src" / "server" / "controlPlane" / "agentGatewayHeartbeatAudit.ts",
        NEXT_APP / "src" / "server" / "controlPlane" / "agentGatewayTasks.ts",
        NEXT_APP / "src" / "server" / "controlPlane" / "auth.ts",
        NEXT_APP / "src" / "server" / "controlPlane" / "config.ts",
        NEXT_APP / "src" / "server" / "controlPlane" / "humanSession.ts",
        NEXT_APP / "src" / "server" / "controlPlane" / "deliveryEvidenceSeal.ts",
        NEXT_APP / "src" / "server" / "controlPlane" / "workspaceReadModels.ts",
        NEXT_APP / "scripts" / "control-plane-mode-contract.ts",
        NEXT_APP / "scripts" / "human-session-timestamp-contract.ts",
        NEXT_APP / "scripts" / "worker-task-pull-claim-contract.ts",
        NEXT_APP / "scripts" / "workspace-read-model-contract.ts",
        NEXT_APP / "scripts" / "schema-migration-upgrade-contract.ts",
        NEXT_APP / "next.config.mjs",
        NEXT_APP / "src" / "components" / "AppFrame.tsx",
        NEXT_APP / "src" / "components" / "AgentsParityPage.tsx",
        NEXT_APP / "src" / "components" / "WorkerConsolePage.tsx",
        NEXT_APP / "src" / "components" / "AgentDetailPage.tsx",
        NEXT_APP / "src" / "components" / "CommercialPage.tsx",
        NEXT_APP / "src" / "components" / "GovernancePage.tsx",
        NEXT_APP / "src" / "components" / "DeploymentPage.tsx",
        NEXT_APP / "src" / "components" / "PixelOfficePage.tsx",
        NEXT_APP / "src" / "components" / "DispatchPage.tsx",
        NEXT_APP / "src" / "components" / "TemplateSwitchingPage.tsx",
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
        ROOT / "scripts" / "ui_covered_route_retirement_packet_smoke.py",
        ROOT / "scripts" / "nextjs_agent_gateway_task_proxy_smoke.py",
        ROOT / "scripts" / "nextjs_agent_gateway_cli_worker_dogfood_smoke.py",
        ROOT / "scripts" / "nextjs_production_python_proxy_fail_closed_smoke.py",
        ROOT / "scripts" / "nextjs_postgres_real_worker_human_review_smoke.py",
        ROOT / "scripts" / "worker_provider_call_evidence_smoke.py",
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
        ROOT / "scripts" / "operator_execution_mode_smoke.py",
        ROOT / "scripts" / "nextjs_template_switching_smoke.py",
        ROOT / "scripts" / "nextjs_control_tower_parity_smoke.py",
        ROOT / "scripts" / "audit_retention_policy_smoke.py",
        ROOT / "scripts" / "audit_retention_controls_smoke.py",
        ROOT / "docs" / "UI_NAVIGATION_INVENTORY.json",
        ROOT / "docs" / "UI_ROUTE_RETIREMENT_PACKET.json",
        ROOT / "docs" / "UI_COVERED_ROUTE_RETIREMENT_PACKET.json",
        ROOT / "docs" / "UI_COVERED_ROUTE_RETIREMENT_PACKET.md",
        ROOT / "docs" / "PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json",
        ROOT / "docs" / "PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.md",
        ROOT / "docs" / "HUMAN_MEMORY_REVIEW_RELEASE_BLOCKERS.json",
    ]

    for path in required_files:
        require(path.exists(), f"missing Next.js parity file: {path.relative_to(ROOT)}")

    server_text = read_text(ROOT / "server.py")
    route_text = read_text(NEXT_APP / "app" / "api" / "mis" / "[...path]" / "route.ts")
    next_config_text = read_text(NEXT_APP / "next.config.mjs")
    gateway_register_route_text = read_text(NEXT_APP / "app" / "api" / "mis" / "agent-gateway" / "register" / "route.ts")
    gateway_heartbeat_route_text = read_text(NEXT_APP / "app" / "api" / "mis" / "agent-gateway" / "heartbeat" / "route.ts")
    gateway_audit_route_text = read_text(NEXT_APP / "app" / "api" / "mis" / "agent-gateway" / "audit" / "route.ts")
    gateway_pull_route_text = read_text(NEXT_APP / "app" / "api" / "mis" / "agent-gateway" / "tasks" / "pull" / "route.ts")
    gateway_claim_route_text = read_text(NEXT_APP / "app" / "api" / "mis" / "agent-gateway" / "tasks" / "[taskId]" / "claim" / "route.ts")
    gateway_heartbeat_audit_text = read_text(NEXT_APP / "src" / "server" / "controlPlane" / "agentGatewayHeartbeatAudit.ts")
    gateway_tasks_text = read_text(NEXT_APP / "src" / "server" / "controlPlane" / "agentGatewayTasks.ts")
    gateway_plans_text = read_text(NEXT_APP / "src" / "server" / "controlPlane" / "agentGatewayPlans.ts")
    gateway_auth_text = read_text(NEXT_APP / "src" / "server" / "controlPlane" / "auth.ts")
    control_plane_config_text = read_text(NEXT_APP / "src" / "server" / "controlPlane" / "config.ts")
    human_session_text = read_text(NEXT_APP / "src" / "server" / "controlPlane" / "humanSession.ts")
    control_plane_mode_contract_text = read_text(NEXT_APP / "scripts" / "control-plane-mode-contract.ts")
    human_session_timestamp_contract_text = read_text(NEXT_APP / "scripts" / "human-session-timestamp-contract.ts")
    worker_task_contract_text = read_text(NEXT_APP / "scripts" / "worker-task-pull-claim-contract.ts")
    workspace_read_models_text = read_text(NEXT_APP / "src" / "server" / "controlPlane" / "workspaceReadModels.ts")
    workspace_read_contract_text = read_text(NEXT_APP / "scripts" / "workspace-read-model-contract.ts")
    approval_decision_contract_text = read_text(NEXT_APP / "scripts" / "approval-decision-contract.ts")
    commercial_ci_text = read_text(ROOT / ".github" / "workflows" / "commercial-migration-ci.yml")
    real_runtime_ci_text = read_text(ROOT / ".github" / "workflows" / "commercial-real-runtime-acceptance.yml")
    schema_readiness_text = read_text(NEXT_APP / "src" / "server" / "controlPlane" / "schemaReadiness.ts")
    schema_readiness_contract_text = read_text(NEXT_APP / "scripts" / "schema-readiness-contract.ts")
    schema_upgrade_contract_text = read_text(NEXT_APP / "scripts" / "schema-migration-upgrade-contract.ts")
    postgres_parity_contract_text = read_text(ROOT / "docs" / "POSTGRES_PARITY_CONTRACT.md")
    workspace_read_route_texts = [
        read_text(NEXT_APP / "app" / "api" / "mis" / route / "route.ts")
        for route in ("tasks", "runs", "approvals", "audit")
    ] + [read_text(NEXT_APP / "app" / "api" / "mis" / "dashboard" / "metrics" / "route.ts")]
    workspace_detail_route_texts = [
        read_text(NEXT_APP / "app" / "api" / "mis" / "tasks" / "[taskId]" / "route.ts"),
        read_text(NEXT_APP / "app" / "api" / "mis" / "runs" / "[runId]" / "route.ts"),
        read_text(NEXT_APP / "app" / "api" / "mis" / "runs" / "[runId]" / "graph" / "route.ts"),
        read_text(NEXT_APP / "app" / "api" / "mis" / "tool-calls" / "route.ts"),
        read_text(NEXT_APP / "app" / "api" / "mis" / "evaluations" / "route.ts"),
    ]
    approval_decision_route_text = read_text(NEXT_APP / "app" / "api" / "mis" / "approvals" / "[approvalId]" / "[decision]" / "route.ts")
    approval_decisions_text = read_text(NEXT_APP / "src" / "server" / "controlPlane" / "approvalDecisions.ts")
    delivery_evidence_seal_text = read_text(NEXT_APP / "src" / "server" / "controlPlane" / "deliveryEvidenceSeal.ts")
    schema_migration_text = read_text(ROOT / "migrations" / "postgres" / "20260719_workspace_read_models_v2.sql")
    schema_online_index_text = read_text(ROOT / "migrations" / "postgres" / "20260719_workspace_read_models_v2_online_indexes.sql")
    approval_schema_migration_text = read_text(ROOT / "migrations" / "postgres" / "20260719_human_approval_decisions_v3.sql")
    approval_kind_schema_migration_text = read_text(ROOT / "migrations" / "postgres" / "20260719_approval_kind_bindings_v4.sql")
    real_worker_human_review_text = read_text(ROOT / "scripts" / "nextjs_postgres_real_worker_human_review_smoke.py")
    worker_provider_evidence_text = read_text(ROOT / "scripts" / "worker_provider_call_evidence_smoke.py")
    approvals_review_route_text = read_text(NEXT_APP / "app" / "workspace" / "approvals" / "review" / "route.ts")
    memory_review_route_text = read_text(NEXT_APP / "app" / "workspace" / "memory" / "review" / "route.ts")
    report_archive_route_text = read_text(NEXT_APP / "app" / "workspace" / "customer-projects" / "[projectId]" / "report" / "archive" / "route.ts")
    dispatch_route_text = read_text(NEXT_APP / "app" / "workspace" / "dispatch" / "template-run" / "route.ts")
    customer_task_route_text = read_text(NEXT_APP / "app" / "workspace" / "dispatch" / "customer-task" / "route.ts")
    template_job_route_text = read_text(NEXT_APP / "app" / "workspace" / "dispatch" / "template-job" / "route.ts")
    customer_worker_dispatch_route_text = read_text(NEXT_APP / "app" / "workspace" / "dispatch" / "customer-worker" / "route.ts")
    customer_worker_job_route_text = read_text(NEXT_APP / "app" / "workspace" / "dispatch" / "customer-worker-job" / "route.ts")
    template_switching_page_route_text = read_text(NEXT_APP / "app" / "workspace" / "templates" / "page.tsx")
    template_switching_preview_route_text = read_text(NEXT_APP / "app" / "workspace" / "templates" / "migration-preview" / "route.ts")
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
    template_switching_page_text = read_text(NEXT_APP / "src" / "components" / "TemplateSwitchingPage.tsx")
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
    production_python_proxy_smoke_text = read_text(ROOT / "scripts" / "nextjs_production_python_proxy_fail_closed_smoke.py")
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
    operator_execution_mode_smoke_text = read_text(ROOT / "scripts" / "operator_execution_mode_smoke.py")
    template_switching_smoke_text = read_text(ROOT / "scripts" / "nextjs_template_switching_smoke.py")
    control_tower_smoke_text = read_text(ROOT / "scripts" / "nextjs_control_tower_parity_smoke.py")
    route_parity_smoke_text = read_text(ROOT / "scripts" / "ui_task_run_route_parity_smoke.py")
    route_alias_smoke_text = read_text(ROOT / "scripts" / "ui_legacy_route_alias_smoke.py")
    navigation_inventory_smoke_text = read_text(ROOT / "scripts" / "ui_navigation_inventory_smoke.py")
    navigation_inventory_text = read_text(ROOT / "docs" / "UI_NAVIGATION_INVENTORY.json")
    retirement_packet_smoke_text = read_text(ROOT / "scripts" / "ui_route_retirement_packet_smoke.py")
    retirement_packet_text = read_text(ROOT / "docs" / "UI_ROUTE_RETIREMENT_PACKET.json")
    covered_retirement_packet_smoke_text = read_text(ROOT / "scripts" / "ui_covered_route_retirement_packet_smoke.py")
    covered_retirement_packet_text = read_text(ROOT / "docs" / "UI_COVERED_ROUTE_RETIREMENT_PACKET.json")
    covered_retirement_packet_doc_text = read_text(ROOT / "docs" / "UI_COVERED_ROUTE_RETIREMENT_PACKET.md")
    human_memory_release_blockers = json.loads(read_text(ROOT / "docs" / "HUMAN_MEMORY_REVIEW_RELEASE_BLOCKERS.json"))
    commercial_ci_receipt_text = read_text(ROOT / "scripts" / "commercial_ci_receipt.py")
    commercial_readiness_text = read_text(ROOT / "scripts" / "commercial_migration_readiness.py")

    require(dependencies.get("next") == "16.2.11", "Next.js version is not pinned to the selected migration version")
    require(dependencies.get("react") == "19.2.7", "React version is not pinned to the selected migration version")
    require(overrides.get("postcss") == "8.5.22" and overrides.get("sharp") == "0.35.3", "Next.js transitive security overrides are not pinned to the audited versions")
    require("build" in scripts and "next build" in scripts["build"], "Next.js build script is missing")
    require(scripts.get("test:control-plane-mode-contract") == "tsx scripts/control-plane-mode-contract.ts", "Production control-plane mode contract script is missing")
    require(scripts.get("test:human-schema-contract") == "tsx scripts/schema-readiness-contract.ts", "Human schema negative contract script is missing")
    require(scripts.get("test:human-session-timestamp-contract") == "tsx scripts/human-session-timestamp-contract.ts", "Human and Agent Gateway timestamp contract script is missing")
    require(scripts.get("test:memory-review-idempotency-contract") == "tsx scripts/memory-review-idempotency-contract.ts", "Memory Review idempotency contract script is missing")
    require(scripts.get("test:worker-gateway-direct-contract") == "tsx scripts/agent-gateway-worker-direct-contract.ts", "Worker register/heartbeat/audit contract script is missing")
    require(scripts.get("test:workspace-read-model-contract") == "tsx scripts/workspace-read-model-contract.ts", "Workspace Human Session read-model contract script is missing")
    require(scripts.get("test:human-schema-upgrade-contract") == "tsx scripts/schema-migration-upgrade-contract.ts", "Human schema v1/v2/v3 to v4 upgrade contract script is missing")
    require(scripts.get("test:worker-task-pull-claim-contract") == "tsx scripts/worker-task-pull-claim-contract.ts", "Worker task pull/claim contract script is missing")
    require("AGENTOPS_API_BASE" in route_text, "Free Local API proxy must be configurable with AGENTOPS_API_BASE")
    require("legacyPythonProxyAllowed" in route_text and "typescript_route_owner_required" in route_text and "python_proxy_performed: false" in route_text, "Commercial production catch-all must fail closed instead of forwarding to Python")
    require(
        "nextjs_production_python_proxy_fail_closed_v2" in production_python_proxy_smoke_text
        and "EXPECTED_COMPILED_API_ROUTE_KEYS" in production_python_proxy_smoke_text
        and "EXPECTED_DIRECT_READ_ROUTE_COUNT = 10" in production_python_proxy_smoke_text
        and "EXPECTED_APPROVAL_DECISION_ROUTE_COUNT = 2" in production_python_proxy_smoke_text
        and "EXPECTED_WORKSPACE_PROXY_ROUTE_COUNT = 16" in production_python_proxy_smoke_text
        and '"compiled_api_route_count": len(compiled_api_routes)' in production_python_proxy_smoke_text
        and "upstream_request_count" in production_python_proxy_smoke_text
        and "python_proxy_performed" in production_python_proxy_smoke_text,
        "Production no-Python smoke must remain scoped to its explicitly enumerated compiled routes and requests",
    )
    require("/api/agent-gateway/:path*" in next_config_text and "/api/mis/agent-gateway/:path*" in next_config_text, "Next must preserve the durable Agent Gateway CLI path while routing it to TypeScript ownership")
    require(all("controlPlaneMode" in text and "proxyControlPlaneRequest" in text for text in (
        gateway_register_route_text, gateway_heartbeat_route_text, gateway_audit_route_text,
        gateway_pull_route_text, gateway_claim_route_text,
    )), "Direct Worker routes must preserve the Free Local proxy path")
    require("registerAgentGatewayWorker" in gateway_register_route_text and "recordAgentGatewayHeartbeat" in gateway_heartbeat_route_text and "emitAgentGatewayAudit" in gateway_audit_route_text, "Worker register/heartbeat/audit routes must have direct TypeScript owners")
    require("pullAgentGatewayTasks" in gateway_pull_route_text and "claimAgentGatewayTask" in gateway_claim_route_text, "Worker pull/claim routes must have direct TypeScript owners")
    require(all("controlPlaneMode" in text and "workspaceReadModels" in text and "X-AgentOps-Workspace-Id" in text for text in workspace_read_route_texts), "Workspace read routes must have direct TypeScript owners, Free Local rollback, and private cookie/workspace cache variance")
    require(all("controlPlaneMode" in text and "workspaceReadModels" in text and "X-AgentOps-Workspace-Id" in text for text in workspace_detail_route_texts), "Workspace detail, graph, tool-call, and evaluation routes must have direct TypeScript owners, Free Local rollback, and private cache variance")
    require("authenticateHumanMember" in workspace_read_models_text and "audit.workspace_id=$1" in workspace_read_models_text and "metadata_json::jsonb ->> 'workspace_id'=$1" in workspace_read_models_text, "Workspace read models must enforce Human Session membership and chain-bound audit workspace binding")
    require("JOIN tasks task" in workspace_read_models_text and "JOIN runs run" in workspace_read_models_text and "run.workspace_id=$1" in workspace_read_models_text, "Approval reads must require matching task/run workspace ownership")
    require("audit.metadata_json," not in workspace_read_models_text and "tamper_chain_hash" not in workspace_read_models_text, "Workspace audit read model must omit raw metadata and chain internals")
    require("nextjs_postgres_workspace_read_models_v1" in workspace_read_contract_text and "authenticated_http_routes_return_private_200" in workspace_read_contract_text, "Workspace read-model Postgres isolation and authenticated HTTP contract is incomplete")
    require("human_memory_schema_readiness_v4" in schema_readiness_contract_text and "v1_v2_v3_v4_migration_bytes_match_fixed_checksums" in schema_readiness_contract_text and "non_deferred_binding_trigger_rejected" in schema_readiness_contract_text and "weak_parent_binding_immutable_trigger_rejected" in schema_readiness_contract_text and "weak_audit_append_only_trigger_rejected" in schema_readiness_contract_text and "update_escape_weak_evidence_seal_function_rejected" in schema_readiness_contract_text, "Human schema v4 exact-readiness contract is incomplete")
    require("human_memory_schema_v1_v2_v3_to_v4_upgrade_v1" in schema_upgrade_contract_text and "exact_v3_receipt_upgraded" in schema_upgrade_contract_text and "approval_kind_is_explicit_without_default" in schema_upgrade_contract_text and "five_approval_kinds_backfilled" in schema_upgrade_contract_text and "deferred_approval_binding_triggers_ready" in schema_upgrade_contract_text and "enrollment_approval_unique_binding_enforced" in schema_upgrade_contract_text and "unclassified_legacy_approval_fails_closed_without_trusted_audit_evidence" in schema_upgrade_contract_text and "mismatched_prefilled_approval_kind_fails_closed" in schema_upgrade_contract_text and "tampered_v1_receipt_rejected_without_ddl" in schema_upgrade_contract_text, "Human schema v1/v2/v3 to v4 upgrade contract is incomplete")
    require('HUMAN_MEMORY_SCHEMA_VERSION = "20260719_approval_kind_bindings_v4"' in schema_readiness_text and 'HUMAN_MEMORY_SCHEMA_CONTRACT = "agentops-human-session-approval-kind-bindings-contract-v4"' in schema_readiness_text, "Human schema readiness owner must require the exact current v4 receipt")
    require("nextjs_postgres_workspace_read_models_v1" in postgres_parity_contract_text, "Workspace read-model Postgres contract is not documented")
    require("ADD COLUMN IF NOT EXISTS workspace_id TEXT" in schema_migration_text and "audit_logs_workspace_metadata_match" in schema_migration_text and "CREATE INDEX" not in schema_migration_text and "CREATE INDEX CONCURRENTLY" in schema_online_index_text, "Postgres audit schema must bind workspace ownership and build its index outside the core transaction")
    require("human_approval_decision_requests" in approval_schema_migration_text and "idempotency_key_hash" in approval_schema_migration_text and "approval_id_fkey" in approval_schema_migration_text, "Postgres Human approval decision idempotency migration is incomplete")
    require("ALTER COLUMN approval_kind DROP DEFAULT" in approval_kind_schema_migration_text and all(f"'{kind}'" in approval_kind_schema_migration_text for kind in ("run_execution", "tool_execution", "prepared_action", "agent_enrollment", "customer_delivery")) and "agentops_enforce_approval_kind_immutable" in approval_kind_schema_migration_text and "approval_terminal_immutable" in approval_kind_schema_migration_text and "approval_binding_immutable" in approval_kind_schema_migration_text and "agentops_enforce_approval_parent_binding_immutable" in approval_kind_schema_migration_text and "agentops_enforce_audit_log_append_only" in approval_kind_schema_migration_text and "approval_kind_backfill_evidence_missing" in approval_kind_schema_migration_text and "approval_kind_prefill_evidence_mismatch" in approval_kind_schema_migration_text and "old_target_run_id" in approval_kind_schema_migration_text and "new_target_run_id" in approval_kind_schema_migration_text and "FOR SHARE OF approval" in approval_kind_schema_migration_text and "agent_plans_customer_delivery_evidence_sealed" in approval_kind_schema_migration_text and "customer_delivery_evidence_sealed" in approval_kind_schema_migration_text and "DEFERRABLE INITIALLY DEFERRED" in approval_kind_schema_migration_text and "AFTER INSERT OR UPDATE OR DELETE" in approval_kind_schema_migration_text and "idx_agent_gateway_enrollment_approval_unique" in approval_kind_schema_migration_text, "Postgres approval-kind v4 migration must enforce five explicit immutable kinds, immutable execution/parent bindings, terminal and audit append-only semantics, evidence-based backfill, serialized decided-delivery evidence sealing, deferred edge binding, DELETE checks, and unique enrollment binding")
    require("decideWorkspaceApproval" in approval_decision_route_text and "human_session_direct_route_required" in approval_decision_route_text and "authenticateHumanReviewer" in approval_decisions_text and "idempotency-key" in approval_decisions_text and "x-agentops-csrf" in human_session_text, "Human approval decisions must have a direct TypeScript/Postgres Human Session owner with CSRF and idempotency")
    require("prepared_action_required" in approval_decisions_text and "verifyLatestWorkspacePlanEvidence" in approval_decisions_text and "customer_delivery_run_incomplete" in approval_decisions_text and "approver_user_id=$2" in approval_decisions_text, "Human approval decisions must fail closed for unsafe high-risk resumes, revalidate delivery evidence and completed-run state, and record the real approver")
    require(all(marker in gateway_plans_text for marker in ("COMMERCIAL_RUNTIME_TYPES", "commercial_runtime_provider_bound", "commercial_worker_tool_provenance", "commercial_mock_evaluation_absent", "commercial_worker_evaluation_provenance", "commercial_artifact_digest_provenance", "commercial_evidence_audit_coverage", "commercial_worker_audit_provenance")) and "artifact.run_id IS NULL AND artifact.task_id=$2" in gateway_plans_text, "Customer-delivery manifest revalidation must bind real Hermes/OpenClaw provider, non-dry-run tool/evaluation/audit provenance, artifact digests, and current-run artifacts")
    require("nextjs_postgres_human_approval_decision_v1" in approval_decision_contract_text and "concurrent_same_key_16_way_single_winner" in approval_decision_contract_text and "customer_delivery_requires_completed_run" in approval_decision_contract_text and "customer_delivery_mock_evidence_rejected" in approval_decision_contract_text and "sibling_run_artifact_excluded_from_delivery_manifest" in approval_decision_contract_text and "customer_delivery_evidence_matrix_sealed" in approval_decision_contract_text and "customer_delivery_evidence_decision_race_serialized" in approval_decision_contract_text and "approval_kind_explicit_immutable_and_edge_bound" in approval_decision_contract_text and "approval_execution_binding_immutable" in approval_decision_contract_text and "enrollment_approval_unique_binding" in approval_decision_contract_text and "enrollment_approval_delete_must_not_orphan_child" in approval_decision_contract_text and "parent_first_lock_order_deadlock_free" in approval_decision_contract_text and "tool_before_approval" in approval_decision_contract_text and "production_python_proxy_blocked" in approval_decision_contract_text, "Human approval decision Postgres behavior contract is incomplete")
    require("assertCustomerDeliveryEvidenceMutable" in delivery_evidence_seal_text and "customer_delivery_evidence_sealed" in delivery_evidence_seal_text, "TypeScript Agent Gateway evidence writes must enforce the decided customer-delivery seal")
    require(scripts.get("test:approval-decision-contract") == "tsx scripts/approval-decision-contract.ts" and "nextjs_postgres_human_approval_decision" in commercial_ci_text and "human_schema_v1_v2_v3_to_v4_upgrade" in commercial_ci_text, "Human approval and v4 schema contracts must be runnable locally and required by Gate 5 CI")
    require("authenticateAgentGateway" in gateway_heartbeat_audit_text and "boundedJsonObject" in gateway_heartbeat_audit_text and "assertExclusiveWorkspaceBinding" in gateway_heartbeat_audit_text, "Worker register/heartbeat/audit ownership must be authenticated, bounded, and workspace-bound")
    require("tasks:read" in gateway_tasks_text and "tasks:claim" in gateway_tasks_text and "pg_advisory_xact_lock" in gateway_tasks_text, "Worker pull/claim ownership must enforce scopes and a single-winner claim lock")
    require("nextjs_postgres_worker_task_pull_claim_v1" in worker_task_contract_text and "planned_to_running_single_winner" in worker_task_contract_text, "Worker pull/claim Postgres contract is incomplete")
    require("nextjs_postgres_real_worker_human_review_v1" in real_worker_human_review_text and "python_api_started" in real_worker_human_review_text and "real_runtime_execution_performed" in real_worker_human_review_text and "real_run_bound_delivery_decisions_completed" in real_worker_human_review_text and "approved_customer_delivery_evidence_sealed" in real_worker_human_review_text and '"worker_created_delivery_approvals": False' in real_worker_human_review_text and '"delivery_approval_creation_source": "acceptance_fixture_bound_to_real_run"' in real_worker_human_review_text, "Real Worker acceptance must distinguish real Runtime evidence from the fixture-bound delivery decision, prove the approved evidence seal, and not attribute approval creation to the Worker")
    require("provider_call_performed" in real_worker_human_review_text and "dry_run" in real_worker_human_review_text, "Real Worker acceptance must distinguish a provider call from a dry run")
    require("worker_provider_call_evidence_v1" in worker_provider_evidence_text and "provider_call_performed" in worker_provider_evidence_text and "dry_run" in worker_provider_evidence_text, "Worker provider-call evidence contract is incomplete")
    require('normalized(process.env.NODE_ENV) === "production"' in control_plane_config_text, "standard next start must be recognized as a production deployment")
    require('if (configured === "proxy") return isProductionDeployment() ? "postgres" : "proxy"' in control_plane_config_text, "production proxy override must fail closed to Postgres ownership")
    require("legacyPythonProxyAllowed" in control_plane_config_text and "FREE_LOCAL_DEPLOYMENT_MODES" in control_plane_config_text, "Python proxy must be restricted to explicit Free Local deployment modes")
    require("AGENTOPS_DEPLOYMENT_MODE must be production" in control_plane_config_text, "Unknown deployment modes must fail closed")
    require("control_plane_production_fail_closed_v1" in control_plane_mode_contract_text and "standard_next_start_defaults_postgres" in control_plane_mode_contract_text and "production_proxy_override_blocked" in control_plane_mode_contract_text and "production_python_catch_all_blocked" in control_plane_mode_contract_text and "production_proxy_helper_blocked" in control_plane_mode_contract_text and "explicit_local_dns_rebinding_blocked" in control_plane_mode_contract_text and "unknown_deployment_mode_rejected" in control_plane_mode_contract_text, "Production control-plane fail-closed contract is incomplete")
    require("humanThrottleTimestampActive" in human_session_text and "humanSessionTimestampExpired" in human_session_text, "Human Session timestamp fail-closed helpers are missing")
    require("agentGatewayTimestampExpired" in gateway_auth_text and "!Number.isFinite(expiresAt)" in gateway_auth_text and "allowMissing" in gateway_auth_text, "Agent Gateway malformed or missing Session expiry must fail closed")
    require("nextHumanLoginFailureState" in human_session_text and "failedClosed" in human_session_text, "Malformed Human login throttle windows must fail closed")
    require("human_session_timestamp_fail_closed_v1" in human_session_timestamp_contract_text and "invalid_gateway_credential_expires" in human_session_timestamp_contract_text and "missing_gateway_session_expiry_expires" in human_session_timestamp_contract_text and "malformed_login_window_blocks" in human_session_timestamp_contract_text, "Human and Agent Gateway malformed timestamp contract is incomplete")
    require(all(marker not in server_text for marker in (
        "workspace_memberships", "human_login_credentials", "human_sessions",
        "human_login_throttle", "human_memory_review_requests",
    )), "Python server must not own commercial Human Session or Memory Review tables")
    require("Workspace control plane" in dashboard_text and "control-tower-live-metrics" in dashboard_text, "Workspace dashboard must expose Control Tower live metrics")
    require("control-tower-split-proof" in dashboard_text and "/workspace/agents agent performance drilldown" in dashboard_text and "/workspace/governance production and session governance" in dashboard_text and "/workspace/deployment BYOC storage and recovery gates" in dashboard_text, "Workspace dashboard must expose split-route Control Tower proof")
    require("control-tower-runtime-health" in dashboard_text and "Runtime health" in dashboard_text, "Workspace dashboard must expose runtime health readback")
    require("control-tower-openclaw-imports" in dashboard_text and "OpenClaw import readback" in dashboard_text, "Workspace dashboard must expose OpenClaw import readback")
    require("control-tower-task-status" in dashboard_text and "Task status distribution" in dashboard_text, "Workspace dashboard must expose task status distribution")
    require("control-tower-cost-leaders" in dashboard_text and "Cost leaders" in dashboard_text, "Workspace dashboard must expose cost leader readback")
    require("nextjs_control_tower_parity_v1" in control_tower_smoke_text and "/workspace/agents" in control_tower_smoke_text and "/workspace/governance" in control_tower_smoke_text and "/workspace/deployment" in control_tower_smoke_text, "Next control tower smoke contract is missing")
    require("/api/mis/dashboard/metrics" in control_tower_smoke_text and "/api/mis/agents" in control_tower_smoke_text and "/api/mis/security/production-readiness" in control_tower_smoke_text and "/api/mis/local/readiness" in control_tower_smoke_text and "/api/mis/storage/backend-status" in control_tower_smoke_text, "Next control tower smoke must exercise dashboard/agents/security/local/storage APIs")
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
    require("TemplateSwitchingPage" in template_switching_page_route_text and "loadServerTemplatePackages" in template_switching_page_route_text and "loadServerBases" in template_switching_page_route_text, "Template switching route must server-load live template/base data")
    require("/migration/preview" in template_switching_preview_route_text and "preview_status" in template_switching_preview_route_text, "Template switching preview form must call MIS migration preview and redirect with proof")
    require("Template Switching" in template_switching_page_text and "template-switching-live-read-model" in template_switching_page_text, "Template switching page must expose live read-model proof")
    require("template-package-catalog" in template_switching_page_text and "/template-packages" in template_switching_page_text, "Template switching page must expose template package catalog")
    require("template-base-switching-plan" in template_switching_page_text and "/bases" in template_switching_page_text, "Template switching page must expose base switching plan")
    require("template-core-ledger-protection" in template_switching_page_text and "Core ledger protection" in template_switching_page_text, "Template switching page must expose local ledger protection")
    require("template-field-mapping" in template_switching_page_text and "/migration/preview" in template_switching_page_text, "Template switching page must expose migration field mapping")
    require("nextjs_template_switching_parity_v1" in template_switching_smoke_text and "/workspace/templates" in template_switching_smoke_text, "Next template switching smoke contract is missing")
    require("/api/mis/template-packages" in template_switching_smoke_text and "/api/mis/bases" in template_switching_smoke_text and "/api/mis/migration/preview" in template_switching_smoke_text, "Next template switching smoke must exercise template/base/preview APIs")
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
    require('AGENTOPS_EDITION"] = "team_governance"' in enrollment_request_smoke_text and '"backend_edition": "team_governance"' in enrollment_request_smoke_text, "Next enrollment request smoke must run approval request flow against a Team Governance entitlement fixture")
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
    require("worker-console-coverage-boundary" in worker_console_page_text and "Worker Console coverage boundary" in worker_console_page_text, "Worker Console must expose covered route boundary proof")
    require("Agent Gateway CLI/API/MCP canonical for token issue/rotate/revoke" in worker_console_page_text and "live daemon lifecycle requires CLI/API operator lane" in worker_console_page_text, "Worker Console must preserve Agent Gateway CLI/API/MCP lifecycle ownership")
    require("worker-console-fleet-lanes" in worker_console_page_text and "Worker fleet lanes" in worker_console_page_text and "/workers/fleet" in worker_console_page_text, "Worker Console must expose fleet lane readback")
    require("worker-console-hygiene-plan" in worker_console_page_text and "Fleet hygiene plan" in worker_console_page_text and "/workers/fleet/hygiene" in worker_console_page_text, "Worker Console must expose read-only hygiene plan")
    require("worker-console-session-hygiene" in worker_console_page_text and "session token omitted" in worker_console_page_text and "session id hidden" in worker_console_page_text, "Worker Console must expose session hygiene without raw ids")
    require("worker-adapter-readiness-proof" in worker_console_page_text and "Adapter readiness" in worker_console_page_text, "Worker Console must expose adapter readiness proof")
    require("operator-execution-mode-readback" in worker_console_page_text and "Operator execution mode" in worker_console_page_text and "/operator/execution-mode" in worker_console_page_text, "Worker Console must expose operator execution-mode readback")
    require("adapter not executed" in worker_console_page_text and "ledger not mutated" in worker_console_page_text and "daemon not started" in worker_console_page_text, "Worker Console must expose execution-mode read-only safety proof")
    require("nextjs_worker_console_parity_v1" in worker_console_smoke_text, "Next Worker Console parity smoke contract is missing")
    require("/workspace/workers" in worker_console_smoke_text and "/api/mis/workers/fleet" in worker_console_smoke_text and "/api/mis/workers/fleet/hygiene" in worker_console_smoke_text and "/api/mis/operator/execution-mode" in worker_console_smoke_text, "Next Worker Console smoke must exercise route plus fleet/hygiene/execution-mode APIs")
    require("Worker Console coverage boundary" in worker_console_smoke_text and "Agent Gateway CLI/API/MCP canonical for token issue/rotate/revoke" in worker_console_smoke_text, "Next Worker Console smoke must enforce the coverage boundary")
    require("mock_daemon_only_next_parity" in worker_console_smoke_text and "gateway_lifecycle_write_not_allowed_next_parity" in worker_console_smoke_text, "Next Worker Console smoke must prove lifecycle writes fail closed")
    require("operator_execution_mode_v1" in operator_execution_mode_smoke_text and "/api/operator/execution-mode" in operator_execution_mode_smoke_text and "agentops operator execution-mode" in operator_execution_mode_smoke_text, "Operator execution-mode smoke contract is missing")
    require("AGENTOPS_API_BASE" in server_lib_text and "loadServerApprovals" in server_lib_text, "server-side first paint loaders are missing")
    require("/dashboard/metrics" in lib_text, "workspace parity data must include dashboard metrics")
    require("loadHumanSession" in dashboard_text and "Select workspace" in dashboard_text and "loadWorkspaceSnapshot(directWorkspace)" in dashboard_text and "setActiveWorkspaceId" in dashboard_text, "Workspace dashboard must require Human Session, propagate active workspace, and require explicit multi-workspace selection for direct Postgres reads")
    require("getActiveWorkspaceId" in lib_text and "agentops_active_workspace" in lib_text, "Workspace ledger clients must propagate the selected workspace across pages")
    require("/tasks" in lib_text and "/runs" in lib_text and "/approvals" in lib_text, "workspace parity data misses core ledgers")
    require("/tool-calls" in lib_text and "loadToolCalls" in lib_text, "tool call ledger parity data is missing")
    require("/evaluations" in lib_text and "loadEvaluations" in lib_text, "evaluation ledger parity data is missing")
    require("/runtime-connectors" in lib_text and "loadRuntimeConnectors" in lib_text, "runtime connector parity data is missing")
    require("updateRuntimeConnectorTrust" in lib_text, "runtime connector trust parity action is missing")
    require("/integrations/notion/status" in lib_text and "loadNotionPreview" in lib_text, "Notion external base parity data is missing")
    require("/integrations/notion/dry-run-export" in lib_text and "/integrations/notion/export-confirmed" in lib_text, "Notion external base export actions are missing")
    require("/memories" in lib_text and 'workspaceReadPath("/audit"' in lib_text and 'limit: "120"' in lib_text, "governance parity data misses memory or audit ledgers")
    require("/workers/status" in lib_text and "/workers/adapter-readiness" in lib_text, "agent-control parity data misses worker readiness")
    require("/workers/fleet" in lib_text and "loadWorkerFleet" in lib_text, "agent-control parity data misses worker fleet readback")
    require("/workers/fleet/hygiene" in lib_text and "loadWorkerFleetHygiene" in lib_text, "agent-control parity data misses worker fleet hygiene readback")
    require("/operator/execution-mode" in lib_text and "loadOperatorExecutionMode" in lib_text, "agent-control parity data misses operator execution-mode readback")
    require("/template-packages" in lib_text and "loadTemplatePackages" in lib_text, "template package parity data is missing")
    require("/template-bindings" in lib_text and "loadTemplateBindings" in lib_text, "template binding parity data is missing")
    require("/bases" in lib_text and "loadBases" in lib_text, "base switching parity data is missing")
    require("loadServerWorkerFleet" in server_lib_text and "/workers/fleet" in server_lib_text, "server-side Worker Console loaders must include fleet readback")
    require("loadServerWorkerFleetHygiene" in server_lib_text and "/workers/fleet/hygiene" in server_lib_text, "server-side Worker Console loaders must include hygiene readback")
    require("loadServerWorkerAdapterReadiness" in server_lib_text and "/workers/adapter-readiness" in server_lib_text, "server-side Worker Console loaders must include adapter readiness")
    require("loadServerOperatorExecutionMode" in server_lib_text and "/operator/execution-mode" in server_lib_text, "server-side Worker Console loaders must include execution-mode readback")
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
    require("decideWorkspaceApproval" in approvals_review_route_text and "/approvals/${encodeURIComponent(approvalId)}/${requestedDecision}" in approvals_review_route_text, "approval review form must use the direct production owner while retaining Free Local MIS API compatibility")
    require("/memories/${encodeURIComponent(memoryId)}/${action}" in memory_review_route_text, "memory review form fallback must write through MIS API")
    require('requestedDecision !== "approve" && requestedDecision !== "reject"' in approvals_review_route_text, "approval review form fallback must reject unknown decisions")
    require('decision !== "approve" && decision !== "reject"' in memory_review_route_text, "memory review form fallback must reject unknown decisions")
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
    require("/workspace/templates" in app_frame_text, "Next.js nav must expose template/base switching parity route")
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
    require("/api/commercial/release-status" in server_text and "commercial_release_status_api_v1" in server_text, "backend must expose read-only commercial release status")
    require("/api/commercial/release-grade-rerun-bundle" in server_text and "commercial_release_grade_rerun_bundle_status" in server_text and "phase_gate_rerun_bundles" in server_text, "backend must expose dynamic read-only release-grade rerun bundle details")
    require("/api/commercial/release-grade-receipt-recording" in server_text and "commercial_release_grade_receipt_recording_status" in server_text and "phase_gate_recording_requests" in server_text, "backend must expose dynamic read-only receipt recording preview details")
    require("include_external_ci_evidence" in server_text and "network_called" in server_text and "commercial_release_external_ci_evidence" in server_text, "backend release status must support explicit external exact-head CI readback")
    require("/commercial/release-status" in lib_text and "CommercialReleaseStatusPayload" in lib_text and "loadCommercialReleaseStatus" in lib_text and "includeExternalCi" in lib_text, "commercial release status parity data is missing")
    require("/commercial/release-grade-rerun-bundle" in lib_text and "CommercialReleaseGradeRerunBundlePayload" in lib_text and "loadCommercialReleaseGradeRerunBundle" in lib_text and "phase_gate_rerun_bundles" in lib_text, "commercial release rerun bundle parity data is missing")
    require("/commercial/release-grade-receipt-recording" in lib_text and "CommercialReleaseGradeReceiptRecordingPayload" in lib_text and "loadCommercialReleaseGradeReceiptRecording" in lib_text and "phase_gate_recording_requests" in lib_text, "commercial receipt recording parity data is missing")
    require("loadServerCommercialReleaseStatus" in server_lib_text and "/commercial/release-status" in server_lib_text and "includeExternalCi" in server_lib_text, "commercial parity page must load server release status")
    require("loadServerCommercialReleaseGradeRerunBundle" in server_lib_text and "/commercial/release-grade-rerun-bundle" in server_lib_text and "includeExternalCi" in server_lib_text, "commercial parity page must load dynamic server rerun bundle details")
    require("loadServerCommercialReleaseGradeReceiptRecording" in server_lib_text and "/commercial/release-grade-receipt-recording" in server_lib_text and "includeExternalCi" in server_lib_text, "commercial parity page must load dynamic receipt recording preview details")
    require("loadServerCommercialReleaseGradeRerunBundle" in read_text(NEXT_APP / "app" / "workspace" / "commercial" / "page.tsx") and "rerunBundle" in read_text(NEXT_APP / "app" / "workspace" / "commercial" / "page.tsx"), "commercial route must load dynamic rerun bundle details")
    require("loadServerCommercialReleaseGradeReceiptRecording" in read_text(NEXT_APP / "app" / "workspace" / "commercial" / "page.tsx") and "receiptRecording" in read_text(NEXT_APP / "app" / "workspace" / "commercial" / "page.tsx"), "commercial route must load dynamic receipt recording preview details")
    require("Release promotion" in commercial_page_text and "Exact-head CI" in commercial_page_text and "Promotion packet" in commercial_page_text and "Receipt promotion plan" in commercial_page_text and "Receipt rerun bundle" in commercial_page_text and "Gate reruns" in commercial_page_text and "write previews" in commercial_page_text and "Receipt recording preview" in commercial_page_text and "Recording previews" in commercial_page_text and "patch previews" in commercial_page_text and "Transaction preview" in commercial_page_text and "CLI confirm only" in commercial_page_text and "--confirm-recording" in commercial_page_text and "Current evidence" in commercial_page_text and "Check exact-head CI" in commercial_page_text, "commercial page must expose release promotion packet, receipt plan, dynamic rerun bundle, recording transaction preview, and current evidence state")
    require("commercial-release-status" in commercial_page_text and "commercial-release-promotion-preflight" in commercial_page_text and "commercial-promotion-packet" in commercial_page_text and "commercial-release-grade-receipt-plan" in commercial_page_text and "commercial-release-grade-rerun-bundle" in commercial_page_text and "commercial-rerun-bundle-gate-detail" in commercial_page_text and "commercial-release-grade-receipt-recording" in commercial_page_text and "commercial-receipt-recording-gate-detail" in commercial_page_text and "commercial-receipt-recording-transaction" in commercial_page_text and "commercial-exact-head-ci-command" in commercial_page_text and "commercial-current-evidence-gates" in commercial_page_text and "commercial-external-ci-readback-form" in commercial_page_text, "commercial page must expose release status smoke markers")
    require("commercial_release_status_api_v1" in commercial_page_text and "commercial_current_evidence_status_v1" in commercial_page_text and "commercial_release_promotion_preflight_v1" in commercial_page_text and "commercial_release_promotion_packet_v1" in commercial_page_text and "commercial_release_grade_receipt_plan_v1" in commercial_page_text and "commercial_release_grade_rerun_bundle_v1" in commercial_page_text and "commercial_release_grade_receipt_recording_v1" in commercial_page_text, "commercial page must render release status contracts")
    require("exact_head_ci" in read_text(NEXT_APP / "app" / "workspace" / "commercial" / "page.tsx") and "includeExternalCi" in read_text(NEXT_APP / "app" / "workspace" / "commercial" / "page.tsx"), "commercial route must expose explicit exact-head CI query controls")
    require("commercial_release_status_api_v1" in read_text(ROOT / "scripts" / "commercial_release_status_api_smoke.py") and "default release status must not call network" in read_text(ROOT / "scripts" / "commercial_release_status_api_smoke.py"), "commercial release status API smoke must prove default no-network and explicit readback")
    require("commercial_release_grade_rerun_bundle_v1" in read_text(ROOT / "scripts" / "commercial_release_grade_rerun_bundle_api_smoke.py") and "default API must not call network" in read_text(ROOT / "scripts" / "commercial_release_grade_rerun_bundle_api_smoke.py"), "commercial rerun bundle API smoke must prove default no-network and no receipt mutation")
    require("commercial_release_grade_receipt_recording_v1" in read_text(ROOT / "scripts" / "commercial_release_grade_receipt_recording_api_smoke.py") and "default API must not call network" in read_text(ROOT / "scripts" / "commercial_release_grade_receipt_recording_api_smoke.py") and "applies_by_default" in read_text(ROOT / "scripts" / "commercial_release_grade_receipt_recording_api_smoke.py"), "commercial receipt recording API smoke must prove default no-network and no receipt mutation")
    require("GovernanceParityPage" in governance_page_text and "Production readiness" in governance_page_text and "Session governance" in governance_page_text, "governance parity page must expose production/session governance")
    require("session id omitted" in governance_page_text and "Audit evidence" in governance_page_text, "governance parity page must avoid raw session ids and expose audit evidence")
    require("Remote enrollment approval" in governance_page_text and "approval_policies" in governance_page_text and "billing call" in governance_page_text, "governance parity page must expose approval-policies entitlement proof")
    require("loadServerSecurityProductionReadiness" in server_lib_text and "loadServerGatewaySessions" in server_lib_text, "governance parity loaders are missing")
    require("/api/mis/commercial/entitlements" in control_tower_smoke_text and "approval_policies" in control_tower_smoke_text and "fail_closed" in control_tower_smoke_text, "control tower smoke must prove Free Local approval-policies entitlement gate through Next")
    require("snapshot_route(next_base, \"/workspace/governance\"" in enrollment_request_smoke_text and "approval_policies" in enrollment_request_smoke_text and "team_governance" in enrollment_request_smoke_text, "enrollment request smoke must prove Team approval-policies gate on Next governance route")
    require("DeploymentParityPage" in deployment_page_text and "Backup and restore evidence" in deployment_page_text and "Storage and retention" in deployment_page_text, "deployment parity page must expose BYOC evidence")
    require("Deployment readiness verdict" in deployment_page_text and "loadServerDeploymentReadiness" in server_lib_text, "deployment parity page must load deployment readiness verdict")
    require("/deployment/readiness" in server_lib_text and "DeploymentReadinessPayload" in lib_text, "deployment readiness loader/type is missing")
    require("/deployment/enterprise-controls" in server_lib_text and "EnterpriseControlsPayload" in lib_text, "enterprise controls loader/type is missing")
    require("raw rows printed false" in deployment_page_text and "Backup restore remains CLI-confirmed" in deployment_page_text, "deployment parity page must keep restore explicit and read-only")
    require("Recovery drill" in deployment_page_text and "Signed export" in deployment_page_text and "signed audit export requires a customer key" in deployment_page_text, "deployment parity page must expose recovery drill and signed audit export readiness")
    require("deployment_checks" in lib_text and "signed_audit_export_contract" in deployment_page_text and "signed_export_tamper_detection" in deployment_page_text, "deployment parity page must consume local deployment checks")
    require("Storage backend migration gate" in deployment_page_text and "writes allowed" in deployment_page_text and "fallback" in deployment_page_text, "deployment parity page must expose storage backend migration gates")
    require("runtime_write_gate" in lib_text and "write_allowlist" in lib_text and "StorageBackendWriteRoute" in lib_text, "storage backend type must expose runtime write gate and allowlist")
    require("storage-runtime-write-contracts" in deployment_page_text and "Fixed runtime prepared-action writes" in deployment_page_text, "deployment parity page must expose fixed runtime prepared-action write gate")
    require("postgres_http_runtime_prepared_action_write_v1" in deployment_page_text and "postgres_http_runtime_approval_decision_write_v1" in deployment_page_text, "deployment parity page must render Postgres runtime write contracts")
    require("/api/integrations/openclaw/probe" in deployment_page_text and "/api/integrations/hermes/run-task" in deployment_page_text and "/api/approvals/:approval_id/approve" in deployment_page_text, "deployment parity page must render the fixed runtime write allowlist")
    require("row_gated_prepared_action_only" in deployment_page_text and "non-fixed runtime" in deployment_page_text, "deployment parity page must prove row-gated approval and non-fixed runtime fail-closed")
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
    require("--postgres-write-fixture" in playwright_smoke_text and "nextjs_deployment_postgres_runtime_write_fixture_v1" in playwright_smoke_text, "browser smoke must expose a focused Postgres write-mode deployment fixture")
    require("verify_deployment_postgres_write_gate" in playwright_smoke_text and "runtime_write_gate" in playwright_smoke_text, "browser smoke must verify Postgres runtime write-gate payloads")
    require("POST /api/integrations/openclaw/probe" in playwright_smoke_text and "POST /api/integrations/hermes/run-task" in playwright_smoke_text and "POST /api/approvals/:approval_id/approve" in playwright_smoke_text, "browser smoke must assert fixed Postgres runtime write routes")
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
    require('"retirement_action": "executed_workspace_redirect"' in retirement_packet_text, "route retirement packet must execute workspace redirect retirement")
    require('"retirement_allowed": true' in retirement_packet_text, "route retirement packet must allow the executed retirement")
    require("executed_admin_operations_workspace_redirect_retirement" in retirement_packet_text, "route retirement packet must record admin-operations execution status")
    require("ui_admin_operations_route_retirement_v1" in retirement_packet_text, "route retirement packet must include the admin-operations retirement contract")
    require("ui_covered_route_retirement_packet_v1" in covered_retirement_packet_smoke_text, "covered-route retirement packet smoke contract is missing")
    require('"retirement_action": "not_executed"' in covered_retirement_packet_text, "covered-route retirement packet must not execute retirement")
    require('"retirement_allowed": false' in covered_retirement_packet_text, "covered-route retirement packet must keep retirement fail-closed")
    require('"control_tower"' in covered_retirement_packet_text and '"/admin"' in covered_retirement_packet_text, "covered-route packet must name the Control Tower /admin candidate")
    require('"worker_console"' in covered_retirement_packet_text and '"/workspace/workers"' in covered_retirement_packet_text, "covered-route packet must name the Worker Console candidates")
    require("agent_gateway_cli_api_mcp_unchanged" in covered_retirement_packet_text, "covered-route packet must preserve Agent Gateway CLI/API/MCP")
    require("does not retire any Vite route" in covered_retirement_packet_doc_text, "covered-route packet doc must keep route retirement fail-closed")
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
    require('action="/workspace/memory/review"' not in governance_pages_text, "commercial memory review must not retain the unsafe Python form fallback")
    require('type="button"' in governance_pages_text, "commercial memory review decisions must use explicit client buttons")
    require("controlPlaneMode() === \"postgres\"" in memory_review_route_text, "legacy memory review route must detect direct Postgres mode")
    require("human_session_direct_route_required" in memory_review_route_text, "legacy memory review route must fail closed in direct Postgres mode")
    require("request.formData()" in memory_review_route_text and "TARGET_BASE" in memory_review_route_text, "legacy memory review route must retain proxy-mode compatibility")
    require(human_memory_release_blockers.get("contract_id") == "human_memory_review_release_blockers_v1", "Human Memory Review release blocker contract is missing")
    require(human_memory_release_blockers.get("release_claim_allowed") is False and human_memory_release_blockers.get("closed_loop_claim_allowed") is False, "Human Memory Review must not claim release closure with open blockers")
    require('"engineering_surface_status"' in commercial_readiness_text and '"release_status"' in commercial_readiness_text, "commercial readiness must separate engineering checks from release eligibility")
    require('"release_claim_allowed": release_ready' in commercial_readiness_text and '"overall_status": "ready" if release_ready else "blocked"' in commercial_readiness_text, "commercial readiness must remain fail closed while release blockers are open")
    require('return 0 if command_ok else 1' in commercial_readiness_text, "commercial readiness exit status must validate the truth contract rather than imply release eligibility")
    require("runtime_security_claims" in commercial_readiness_text and "github_run_verified" in commercial_readiness_text and "max_age_hours" in commercial_readiness_text, "commercial readiness must bind fresh runtime security claims to a verified successful GitHub run")
    blocker_ids = {item.get("id") for item in human_memory_release_blockers.get("open_blockers", [])}
    require({"production_api_route_ownership_incomplete", "trusted_proxy_ip_edge_rate_limit_required", "historical_audit_workspace_backfill_missing", "human_session_retention_job_missing", "human_memory_review_request_retention_policy_missing", "approval_decision_request_retention_policy_missing", "approval_expiry_reconciliation_missing", "typescript_approval_policy_entitlement_owner_missing", "production_prepared_action_resume_ownership_missing", "production_enrollment_issue_owner_missing", "production_customer_delivery_approval_creation_owner_missing", "exact_head_real_runtime_receipt_missing", "trusted_real_runtime_builder_not_established", "trusted_runtime_identity_attestation_missing", "receipt_verifier_binary_trust_missing", "ordinary_high_risk_tool_execution_receipt_missing", "owner_bootstrap_compiled_entry_missing"}.issubset(blocker_ids), "Human Memory Review release blockers are incomplete")
    require({"approval_kind_binding_missing", "enrollment_approval_unique_binding_missing"}.isdisjoint(blocker_ids), "Closed v4 approval schema blockers must not remain open")
    require(human_memory_release_blockers.get("local_precommit_observations", {}).get("scope") == "non_release_engineering_observation", "local real Runtime observations must be explicitly non-release evidence")
    require(human_memory_release_blockers.get("local_precommit_observations", {}).get("real_openclaw_worker_human_review_bridge_observed") is True, "local OpenClaw Worker to Human Review observation is not recorded")
    require(human_memory_release_blockers.get("local_precommit_observations", {}).get("real_hermes_worker_human_review_bridge_observed") is True, "local Hermes Worker to Human Review observation is not recorded")
    require(human_memory_release_blockers.get("local_precommit_observations", {}).get("real_openclaw_run_bound_delivery_decision_observed") is True, "local OpenClaw run-bound delivery decision observation is not recorded")
    require(human_memory_release_blockers.get("local_precommit_observations", {}).get("real_hermes_run_bound_delivery_decision_observed") is True, "local Hermes run-bound delivery decision observation is not recorded")
    runtime_receipt_requirement = human_memory_release_blockers.get("external_runtime_receipt_requirement", {})
    require(runtime_receipt_requirement.get("contract_id") == "commercial_ci_command_receipt_v1" and runtime_receipt_requirement.get("workflow") == "commercial-real-runtime-acceptance", "external exact-head Runtime receipt contract is not recorded")
    require(runtime_receipt_requirement.get("repository") == "geogejoy107-jpg/agentops-mis-mvp" and runtime_receipt_requirement.get("signer_workflow", "").endswith("/.github/workflows/commercial-real-runtime-acceptance.yml"), "external exact-head Runtime signer identity is not pinned")
    require(set(runtime_receipt_requirement.get("required_adapters") or []) == {"hermes", "openclaw"}, "external exact-head Runtime receipt must require both real adapters")
    require(set(runtime_receipt_requirement.get("allowed_refs") or []) == {"refs/heads/main"} and runtime_receipt_requirement.get("builder_must_differ_from_candidate_authority") is True, "external Runtime signer must be restricted to trusted main while binding a separate candidate subject")
    require("actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6" in real_runtime_ci_text and "human-memory-real-runtime.attestation.json" in real_runtime_ci_text, "real Runtime workflow must emit a pinned signed offline attestation bundle")
    require("workflow_dispatch:" in real_runtime_ci_text and "github.ref == 'refs/heads/main'" in real_runtime_ci_text and "path: trusted" in real_runtime_ci_text and "path: candidate" in real_runtime_ci_text and "push:" not in real_runtime_ci_text and "continue-on-error" not in real_runtime_ci_text and "environment: commercial-real-runtime" in real_runtime_ci_text, "real Runtime workflow must use only the trusted-main dual-checkout dispatch path and protected environment")
    require("npm --prefix candidate/ui/next-app ci --ignore-scripts" in real_runtime_ci_text and "--subject-sha" in real_runtime_ci_text and "--builder-sha" in real_runtime_ci_text and "--source-root" in real_runtime_ci_text and "trusted/scripts/nextjs_postgres_real_worker_human_review_smoke.py" in real_runtime_ci_text and "AGENTOPS_REAL_RUNTIME_POSTGRES_DSN" in real_runtime_ci_text, "trusted Runtime workflow must test candidate source with a trusted harness, separate subject/builder identity, disabled install scripts, and bounded credentials")
    require("runtime_security_claims" in commercial_ci_receipt_text and "real_runtime_security_claims_incomplete" in commercial_ci_receipt_text and "approved_customer_delivery_evidence_sealed" in commercial_ci_receipt_text, "external Runtime receipt must retain bounded security claims including the approved-delivery evidence seal")
    require(
        all(
            marker in commercial_readiness_text
            for marker in (
                '"gh"',
                '"attestation"',
                '"verify"',
                '"--predicate-type"',
                '"--signer-digest"',
                '"--source-digest"',
                '"--source-ref"',
            )
        ),
        "commercial readiness must cryptographically verify the external Runtime receipt predicate, signer, source commit, and ref",
    )
    require(human_memory_release_blockers.get("implemented_controls", {}).get("approval_kind_v4_explicit_without_default") is True, "explicit no-default approval kind v4 control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("approval_kind_v4_immutable_and_edge_bound") is True, "immutable edge-bound approval kind v4 control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("approval_execution_binding_immutable") is True, "immutable approval execution binding control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("approval_parent_binding_immutable") is True, "immutable approval parent binding control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("approval_terminal_state_immutable") is True, "terminal approval immutability control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("legacy_approval_kind_backfill_unclassified_fails_closed") is True, "legacy approval-kind evidence backfill control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("enrollment_approval_unique_binding_enforced") is True, "unique enrollment approval binding control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("audit_log_append_only") is True, "append-only audit control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("customer_delivery_evidence_sealed_after_decision") is True, "customer-delivery evidence seal control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("customer_delivery_agent_plan_sealed_after_decision") is True, "customer-delivery Agent Plan seal control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("customer_delivery_evidence_decision_race_serialized") is True, "customer-delivery evidence/decision serialization control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("plan_evidence_complete_tool_evaluation_artifact_set") is True, "complete plan-evidence ledger control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("plan_evidence_audit_ids_server_derived") is True, "server-derived audit evidence control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("external_runtime_receipt_security_claims_required") is True, "external Runtime security-claim receipt control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("commercial_delivery_real_runtime_provenance_revalidated") is True, "commercial delivery real Runtime provenance control is not recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("trusted_default_branch_candidate_harness_defined") is True, "trusted default-branch candidate harness control is not recorded")
    require(human_memory_release_blockers.get("acceptance_evidence", {}).get("worker_created_delivery_approvals") is False, "Worker acceptance must not claim production delivery-approval creation")
    require(human_memory_release_blockers.get("acceptance_evidence", {}).get("delivery_approval_creation_source") == "acceptance_fixture_bound_to_real_run", "run-bound delivery approval fixture source is not recorded")
    require(human_memory_release_blockers.get("acceptance_evidence", {}).get("evidence_scope") == "local_precommit_engineering_only", "real Runtime evidence scope must remain pre-commit until an external exact-HEAD receipt exists")
    require(human_memory_release_blockers.get("acceptance_evidence", {}).get("subject_sha") is None and human_memory_release_blockers.get("acceptance_evidence", {}).get("exact_head") is False and human_memory_release_blockers.get("acceptance_evidence", {}).get("release_authority") is False, "committed runtime evidence must not self-attest exact-HEAD release authority")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("free_local_legacy_workspace_mutation_same_origin_enforced") is True, "Free Local legacy Workspace writes must stay same-origin")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("legacy_review_decisions_fail_closed") is True, "legacy review forms must reject unknown decisions")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("production_shared_python_proxy_helper_blocked") is True, "shared production proxy helper must never reach Python")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("workspace_detail_read_routes_typescript_postgres_owned") is True, "workspace detail read ownership must be recorded")
    require(human_memory_release_blockers.get("implemented_controls", {}).get("human_approval_decision_route_typescript_postgres_owned") is True, "Human approval decision ownership must be recorded")
    require("plan_evidence_expected_steps_conflict" in gateway_plans_text and "expected_steps_match_plan" in gateway_plans_text, "plan-evidence expected steps must remain server-derived from the locked Agent Plan")
    require("tool_evidence_complete" in gateway_plans_text and "evaluation_evidence_complete" in gateway_plans_text and "artifact_evidence_complete" in gateway_plans_text and "audit_ids_server_derived" in gateway_plans_text, "plan-evidence verification must cover the complete authoritative run/task evidence set and derive audit IDs server-side")
    require(
        "manifest_authority_guards_passed" in real_worker_human_review_text
        and "selective success-only evidence was not blocked" in real_worker_human_review_text
        and "customer_delivery_revalidation_blocked" in real_worker_human_review_text
        and "approved_customer_delivery_evidence_sealed" in real_worker_human_review_text
        and '"next_runtime_mode": "production_start"' in real_worker_human_review_text
        and "next_artifact_sha256" in real_worker_human_review_text
        and "tracked_worktree_unchanged" in real_worker_human_review_text
        and "verified_plan_evidence_manifest_required" in real_worker_human_review_text,
        "real Runtime acceptance must use a hashed production Next artifact and retain negative plan-evidence authority, Human delivery revalidation, and approved evidence-seal guards",
    )
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
            "/workspace/templates",
            "/workspace/templates/migration-preview",
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
            "operator_execution_mode_v1",
            "nextjs_template_switching_parity_v1",
            "nextjs_control_tower_parity_v1",
            "ui_covered_route_retirement_packet_v1",
        ],
        "stack": {
            "next": dependencies.get("next"),
            "react": dependencies.get("react"),
            "typescript": package.get("devDependencies", {}).get("typescript"),
        },
        "free_local_api_provider": "AGENTOPS_API_BASE or http://127.0.0.1:8765/api",
        "commercial_production_catch_all": "blocked_requires_typescript_route_owner",
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
