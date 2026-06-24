#!/usr/bin/env python3
"""Read-only commercial migration readiness checker.

The checker intentionally avoids contacting external services. It verifies that
the commercial migration lane has the core docs, current product stack, branch
isolation, and no obvious generated/runtime artifacts in the pending change set.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BLOCKED_PATH_PARTS = (
    "node_modules/",
    "/dist/",
    ".agentops_runtime/",
    "__pycache__/",
)
BLOCKED_SUFFIXES = (
    ".db",
    ".db-journal",
    ".db-shm",
    ".db-wal",
    ".env",
    ".log",
)


def run_git(args: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        return False, str(exc)
    output = result.stdout.strip() or result.stderr.strip()
    return result.returncode == 0, output


def file_contains(path: str, needle: str) -> bool:
    target = ROOT / path
    if not target.exists():
        return False
    return needle in target.read_text(encoding="utf-8", errors="replace")


def read_json(path: str) -> dict:
    target = ROOT / path
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def route_naming_decision_semantics_ok() -> bool:
    decision = read_json("docs/UI_ROUTE_NAMING_DECISION.json")
    if decision.get("contract_id") != "ui_route_naming_decision_v1":
        return False
    if decision.get("status") != "accepted_no_route_retirement":
        return False
    policy = decision.get("policy") or {}
    if policy.get("legacy_namespace") != "/admin" or policy.get("target_namespace") != "/workspace":
        return False
    if policy.get("alias_contract") != "ui_legacy_route_alias_v1":
        return False
    if policy.get("navigation_inventory_contract") != "ui_navigation_inventory_v1":
        return False
    if policy.get("retirement_packet_contract") != "ui_route_retirement_packet_v1":
        return False
    if policy.get("retirement_allowed_by_default") is not False:
        return False
    if policy.get("redirects_required_before_retirement") is not True:
        return False
    required = {
        "task_detail": ("/admin/tasks/:id", "/workspace/tasks/:taskId"),
        "run_ledger": ("/admin/runs", "/workspace/runs"),
        "run_detail": ("/admin/runs/:id", "/workspace/runs/:runId"),
    }
    required_cutover = {
        "route_level_read_model_parity",
        "vite_and_next_browser_snapshot_parity",
        "backward_compatible_redirect_or_alias",
        "navigation_inventory_update",
        "explicit_route_retirement_commit",
    }
    pairs = {str(pair.get("id")): pair for pair in decision.get("route_pairs") or [] if isinstance(pair, dict)}
    for pair_id, (legacy, target) in required.items():
        pair = pairs.get(pair_id) or {}
        if pair.get("legacy_route") != legacy or pair.get("target_route") != target:
            return False
        if pair.get("next_alias_status") != "redirects_to_target_route":
            return False
        if "backward_compatible_redirect_or_alias" not in set(pair.get("cutover_evidence") or []):
            return False
        if "canonical_navigation_inventory_verified" not in set(pair.get("cutover_evidence") or []):
            return False
        if "retirement_packet_prepared" not in set(pair.get("cutover_evidence") or []):
            return False
        if set(pair.get("remaining_cutover_requires") or []) != {"explicit_route_retirement_commit"}:
            return False
        if pair.get("retirement_allowed") is not False:
            return False
        if not required_cutover.issubset(set(pair.get("cutover_requires") or [])):
            return False
    return True


def status_paths() -> list[str]:
    ok, output = run_git(["status", "--short"])
    if not ok or not output:
        return []
    paths = []
    for line in output.splitlines():
        raw = line[2:].strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1].strip()
        paths.append(raw.strip('"'))
    return paths


def blocked_status_paths(paths: list[str]) -> list[str]:
    blocked = []
    for path in paths:
        normalized = path.replace("\\", "/")
        with_slashes = f"/{normalized}"
        if any(part in normalized or part in with_slashes for part in BLOCKED_PATH_PARTS):
            blocked.append(path)
            continue
        if any(normalized.endswith(suffix) for suffix in BLOCKED_SUFFIXES):
            blocked.append(path)
    return blocked


def check(name: str, ok: bool, detail: str, command: str | None = None) -> dict:
    item = {
        "name": name,
        "ok": bool(ok),
        "detail": detail,
    }
    if command:
        item["command"] = command
    return item


def main() -> int:
    branch_ok, branch = run_git(["branch", "--show-current"])
    paths = status_paths()
    blocked_paths = blocked_status_paths(paths)

    required_docs = [
        "docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md",
        "docs/PRICING_AND_ENTITLEMENT_DRAFT.md",
        "docs/TECHNICAL_SOLUTION.md",
        "docs/PARALLEL_PRODUCT_DELIVERY_BRANCH_PLAN.md",
        "docs/CODEX_NEXTJS_HANDOFF_PROMPT.md",
        "docs/STORAGE_BOUNDARY_MAP.md",
        "docs/POSTGRES_PARITY_CONTRACT.md",
        "docs/RELEASE_EVIDENCE_PACKET.md",
        "docs/RELEASE_EVIDENCE_PACKET.json",
        "docs/RELEASE_FREEZE_PROTOCOL.md",
        "docs/RELEASE_FREEZE_PROTOCOL.json",
        "docs/MERGE_READINESS_STATUS.md",
        "docs/MERGE_READINESS_STATUS.json",
        "docs/COMMERCIAL_EVIDENCE_RECEIPTS.md",
        "docs/COMMERCIAL_EVIDENCE_RECEIPTS.json",
        "docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md",
        "docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json",
        "docs/COMMERCIAL_HANDOFF_STATUS.md",
        "docs/COMMERCIAL_HANDOFF_STATUS.json",
        "docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.md",
        "docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json",
        "docs/UI_ROUTE_NAMING_DECISION.md",
        "docs/UI_ROUTE_NAMING_DECISION.json",
        "docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.md",
        "docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json",
    ]
    required_stack = [
        "server.py",
        "agentops_mis_cli/agentops.py",
        "sql/schema.sql",
        "config/entitlements.example.json",
        "ui/start-building-app/package.json",
        "ui/next-app/package.json",
    ]

    checks = [
        check(
            "isolated_commercial_branch",
            branch_ok and branch.startswith("codex/") and branch not in {"main", "codex/agent-gateway-kb-demo"},
            f"current_branch={branch or 'unknown'}",
            "git branch --show-current",
        ),
        check(
            "required_migration_docs_present",
            all((ROOT / path).exists() for path in required_docs),
            "required_docs=" + ",".join(required_docs),
        ),
        check(
            "current_product_stack_present",
            all((ROOT / path).exists() for path in required_stack),
            "required_stack=" + ",".join(required_stack),
        ),
        check(
            "no_big_bang_decision_recorded",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "There is no big-bang rewrite"),
            "commercial migration doc keeps current Python/SQLite/Vite line valid until parity gates pass",
        ),
        check(
            "production_readiness_surface_exists",
            file_contains("server.py", "/api/security/production-readiness")
            and file_contains("agentops_mis_cli/agentops.py", "production-readiness")
            and file_contains("scripts/production_auth_fail_closed_smoke.py", "--configured-production-fixture")
            and file_contains("scripts/production_auth_fail_closed_smoke.py", "AGENTOPS_DEPLOYMENT_MODE")
            and file_contains("scripts/production_auth_fail_closed_smoke.py", "read_only_hash_checked")
            and file_contains("scripts/security_production_readiness_smoke.py", "--configured-production-fixture")
            and file_contains("scripts/security_production_readiness_smoke.py", "AGENTOPS_DEPLOYMENT_MODE")
            and file_contains("scripts/security_production_readiness_smoke.py", "validate_configured_blocked")
            and file_contains("scripts/security_production_readiness_smoke.py", "validate_configured_ready")
            and file_contains("scripts/security_production_readiness_smoke.py", "prod-api-key-fixture")
            and file_contains("scripts/security_production_readiness_smoke.py", "admin_key_list_status")
            and file_contains("scripts/security_production_readiness_smoke.py", "db_dump_hash"),
            "server API, CLI production-readiness command, and configured production blocked/ready fixture are present",
        ),
        check(
            "gate2_isolated_governance_fixtures_exist",
            file_contains("scripts/smoke_isolated_server.py", "isolated_server")
            and file_contains("scripts/agent_gateway_scope_matrix_smoke.py", "--isolated-fixture")
            and file_contains("scripts/agent_gateway_scope_matrix_smoke.py", "submit_verified_agent_plan")
            and file_contains("scripts/workspace_isolation_smoke.py", "--isolated-fixture")
            and file_contains("scripts/workspace_isolation_smoke.py", "submit_verified_agent_plan")
            and file_contains("scripts/workspace_rbac_governance_smoke.py", "--isolated-fixture")
            and file_contains("scripts/workspace_memory_session_governance_smoke.py", "--isolated-fixture"),
            "Gate 2 workspace/scope governance smokes can start isolated temporary servers and avoid live ledger contamination",
        ),
        check(
            "local_runtime_acceptance_surface_exists",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "local_runtime_acceptance.py --live-openclaw --live-hermes")
            and file_contains("scripts/local_runtime_acceptance.py", '"agent-plan"')
            and file_contains("scripts/local_runtime_acceptance.py", '"plan-evidence"')
            and file_contains("scripts/local_runtime_acceptance.py", "Agent Plan verification did not pass")
            and file_contains("scripts/local_runtime_acceptance.py", "Plan evidence manifest did not verify")
            and file_contains("scripts/local_runtime_acceptance.py", "prepared_runtime_prepare_payload")
            and file_contains("scripts/local_runtime_acceptance.py", "prepared_action_status")
            and file_contains("scripts/local_runtime_acceptance.py", '"prepared_action_id"')
            and file_contains("scripts/local_runtime_acceptance.py", "Prepared runtime probe did not consume")
            and (ROOT / "scripts" / "local_runtime_acceptance.py").exists(),
            "Real Hermes/OpenClaw runtime acceptance requires Agent Plan-gated run start, verified plan-evidence, unique prepared actions, and consumed prepared actions",
        ),
        check(
            "entitlement_direction_recorded",
            file_contains("docs/PRICING_AND_ENTITLEMENT_DRAFT.md", "Enterprise / BYOC")
            and file_contains("docs/PRICING_AND_ENTITLEMENT_DRAFT.md", "Free Local"),
            "edition ladder exists in pricing/entitlement draft",
        ),
        check(
            "entitlement_fail_closed_surface_exists",
            file_contains("server.py", "/api/commercial/entitlements")
            and file_contains("agentops_mis_cli/agentops.py", "commercial_entitlements")
            and file_contains("server.py", "COMMERCIAL_FAIL_CLOSED_CAPABILITIES")
            and file_contains("server.py", '"approval_policies"')
            and file_contains("scripts/commercial_entitlements_smoke.py", "validate_entitlement_audit")
            and file_contains("scripts/commercial_entitlements_smoke.py", "validate_pro_template_run")
            and file_contains("scripts/commercial_entitlements_smoke.py", "fail_closed")
            and file_contains("scripts/team_entitlement_enrollment_smoke.py", "validate_downgrade_issue_block")
            and file_contains("scripts/team_entitlement_enrollment_smoke.py", "team_governance")
            and (ROOT / "scripts" / "commercial_entitlements_smoke.py").exists()
            and (ROOT / "scripts" / "team_entitlement_enrollment_smoke.py").exists(),
            "commercial entitlement API/CLI has fail-closed gates, audit evidence, Pro allow-path, and Team enrollment-policy smoke coverage",
        ),
        check(
            "nextjs_is_gated_not_immediate",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "UI/API Parity Before Next.js"),
            "Next.js migration is behind a parity gate",
        ),
        check(
            "nextjs_parity_surface_exists",
            file_contains("ui/next-app/package.json", '"next": "16.2.9"')
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "AGENTOPS_API_BASE")
            and file_contains("ui/next-app/src/lib/mis.ts", "/dashboard/metrics")
            and file_contains("ui/next-app/src/lib/mis.ts", "/storage/backend-status")
            and file_contains("ui/next-app/src/lib/mis.ts", "/tool-calls")
            and file_contains("ui/next-app/src/lib/mis.ts", "/evaluations")
            and file_contains("ui/next-app/src/lib/mis.ts", "/runtime-connectors")
            and file_contains("ui/next-app/src/lib/mis.ts", "/integrations/notion/status")
            and file_contains("ui/next-app/src/lib/mis.ts", "/agents/${encodeURIComponent(agentId)}/performance")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerStorageBackendStatus")
            and file_contains("ui/next-app/src/components/AgentDetailPage.tsx", "AgentDetailParityPage")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "Storage backend migration gate")
            and file_contains("ui/next-app/src/components/ToolCallPages.tsx", "ToolCallsParityPage")
            and file_contains("ui/next-app/src/components/EvaluationPages.tsx", "EvaluationsParityPage")
            and file_contains("ui/next-app/src/components/ConnectorPages.tsx", "RuntimeConnectorsParityPage")
            and file_contains("ui/next-app/src/components/NotionBasePage.tsx", "NotionExternalBaseParityPage")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", "/workspace/tool-calls")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", "/workspace/evaluations")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", "/workspace/connectors")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", "/workspace/external-bases/notion")
            and file_contains("scripts/nextjs_agent_gateway_task_proxy_smoke.py", "nextjs_agent_gateway_task_proxy_v1")
            and file_contains("scripts/nextjs_agent_gateway_task_proxy_smoke.py", "/api/mis/agent-gateway/tasks")
            and file_contains("scripts/nextjs_agent_gateway_task_proxy_smoke.py", "no_token_status == 401")
            and file_contains("scripts/nextjs_agent_gateway_task_proxy_smoke.py", "direct_api_matches_next_proxy")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_agent_gateway_task_proxy_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_agent_gateway_cli_worker_dogfood_v1")
            and file_contains("scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py", "nextjs_agent_gateway_cli_worker_dogfood_v1")
            and file_contains("scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py", "/api/mis/agent-gateway/tasks")
            and file_contains("scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py", "scripts/agent_worker.py --once --adapter mock")
            and file_contains("scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py", "plan-evidence-manifests/:id/verify")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "mock_only_next_parity")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "isWorkerDispatchPath")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "force_release_not_allowed_next_parity")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "isWorkerReleasePath")
            and file_contains("ui/next-app/src/lib/mis.ts", "/workers/local/dispatch-once")
            and file_contains("ui/next-app/src/lib/mis.ts", "mock_only_next_parity")
            and file_contains("ui/next-app/src/lib/mis.ts", "/workers/tasks/release")
            and file_contains("ui/next-app/src/lib/mis.ts", "/workers/local/start")
            and file_contains("ui/next-app/src/lib/mis.ts", "/workers/local/stop")
            and file_contains("ui/next-app/src/lib/mis.ts", "/workers/local/restart")
            and file_contains("ui/next-app/src/lib/mis.ts", "/agent-gateway/enrollments")
            and file_contains("ui/next-app/src/lib/mis.ts", "/agent-gateway/enrollment/policy-preview")
            and file_contains("ui/next-app/src/lib/mis.ts", "/agent-gateway/enrollment/request")
            and file_contains("ui/next-app/src/components/AgentsParityPage.tsx", "dispatchLocalWorkerOnce")
            and file_contains("ui/next-app/src/components/AgentsParityPage.tsx", "releaseWorkerTask")
            and file_contains("ui/next-app/src/components/AgentsParityPage.tsx", "startMockWorkerDaemon")
            and file_contains("ui/next-app/src/components/AgentsParityPage.tsx", "stopMockWorkerDaemon")
            and file_contains("ui/next-app/src/components/AgentsParityPage.tsx", "requestAgentGatewayEnrollment")
            and file_contains("ui/next-app/app/workspace/agents/dispatch-once/route.ts", "/workers/local/dispatch-once")
            and file_contains("ui/next-app/app/workspace/agents/dispatch-once/route.ts", "mock_only_next_parity")
            and file_contains("ui/next-app/app/workspace/agents/release-task/route.ts", "/workers/tasks/release")
            and file_contains("ui/next-app/app/workspace/agents/release-task/route.ts", "task_id_required")
            and file_contains("ui/next-app/app/workspace/agents/daemon-control/route.ts", "/workers/local/${action}")
            and file_contains("ui/next-app/app/workspace/agents/daemon-control/route.ts", "mock_daemon_only_next_parity")
            and file_contains("ui/next-app/app/workspace/agents/enrollment-request/route.ts", "/agent-gateway/enrollment/request")
            and file_contains("ui/next-app/app/workspace/agents/enrollment-request/route.ts", "invalid_scopes")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "enrollment_token_issue_not_allowed_next_parity")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "mock_daemon_only_next_parity")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "live_worker_daemon_not_allowed_next_parity")
            and file_contains("scripts/nextjs_worker_dispatch_once_smoke.py", "nextjs_worker_dispatch_once_v1")
            and file_contains("scripts/nextjs_worker_dispatch_once_smoke.py", "/api/mis/workers/local/dispatch-once")
            and file_contains("scripts/nextjs_worker_dispatch_once_smoke.py", "mock_only_next_parity")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "isCustomerWorkerWorkflowPath")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "customerWorkerWorkflowGuard")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "prepared_action_required")
            and file_contains("ui/next-app/app/workspace/pixel-office/page.tsx", "PixelOfficeParityPage")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "Pixel Operating Map")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "Local brief controls")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "/workspace/pixel-office/local-brief")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "commercial-safe geometry")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "live runtime disabled")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "live brief approval-gated")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "Resume approved brief")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "isLocalBriefPath")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "prepared_action_required")
            and file_contains("ui/next-app/app/workspace/pixel-office/local-brief/route.ts", "/workflows/local-brief")
            and file_contains("ui/next-app/app/workspace/pixel-office/local-brief/route.ts", "prepared_action_id")
            and file_contains("ui/next-app/app/workspace/pixel-office/local-brief/route.ts", "approval_required")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", "/workspace/pixel-office")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerDashboardMetrics")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerAgents")
            and file_contains("scripts/nextjs_pixel_office_floor_smoke.py", "nextjs_pixel_office_floor_v1")
            and file_contains("scripts/nextjs_pixel_office_floor_smoke.py", "/workspace/pixel-office")
            and file_contains("scripts/nextjs_pixel_office_floor_smoke.py", "Owner dispatch workflow")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "owner-dispatch-workflow")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "template intake /workspace/dispatch")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "delivery reports /workspace/reports")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "control-tower-live-metrics")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "control-tower-split-proof")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "/workspace/agents agent performance drilldown")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "control-tower-runtime-health")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "control-tower-openclaw-imports")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "control-tower-task-status")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "control-tower-cost-leaders")
            and file_contains("scripts/nextjs_control_tower_parity_smoke.py", "nextjs_control_tower_parity_v1")
            and file_contains("scripts/nextjs_control_tower_parity_smoke.py", "/api/mis/dashboard/metrics")
            and file_contains("scripts/nextjs_control_tower_parity_smoke.py", "/api/mis/agents")
            and file_contains("scripts/nextjs_control_tower_parity_smoke.py", "/api/mis/security/production-readiness")
            and file_contains("scripts/nextjs_control_tower_parity_smoke.py", "/api/mis/local/readiness")
            and file_contains("scripts/nextjs_control_tower_parity_smoke.py", "/api/mis/storage/backend-status")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-task/route.ts", "/workflows/customer-task")
            and file_contains("ui/next-app/app/workspace/dispatch/template-job/route.ts", "/workflows/customer-task-templates/submit")
            and file_contains("ui/next-app/app/workspace/dispatch/page.tsx", "loadServerAgents")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "Owner task composer")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "/workspace/dispatch/customer-task")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "/workspace/dispatch/template-job")
            and file_contains("ui/next-app/app/workspace/templates/page.tsx", "TemplateSwitchingPage")
            and file_contains("ui/next-app/app/workspace/templates/page.tsx", "loadServerTemplatePackages")
            and file_contains("ui/next-app/app/workspace/templates/page.tsx", "loadServerBases")
            and file_contains("ui/next-app/app/workspace/templates/migration-preview/route.ts", "/migration/preview")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "Template Switching")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "template-switching-live-read-model")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "template-base-switching-plan")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "template-core-ledger-protection")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "/template-packages")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "/bases")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "/migration/preview")
            and file_contains("ui/next-app/src/lib/mis.ts", "loadTemplatePackages")
            and file_contains("ui/next-app/src/lib/mis.ts", "loadTemplateBindings")
            and file_contains("ui/next-app/src/lib/mis.ts", "loadBases")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerTemplatePackages")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerTemplateBindings")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerBases")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", "/workspace/templates")
            and file_contains("scripts/nextjs_template_switching_smoke.py", "nextjs_template_switching_parity_v1")
            and file_contains("scripts/nextjs_template_switching_smoke.py", "/workspace/templates")
            and file_contains("scripts/nextjs_template_switching_smoke.py", "/api/mis/template-packages")
            and file_contains("scripts/nextjs_template_switching_smoke.py", "/api/mis/bases")
            and file_contains("scripts/nextjs_template_switching_smoke.py", "/api/mis/migration/preview")
            and file_contains("scripts/nextjs_pixel_office_dispatch_smoke.py", "nextjs_pixel_office_dispatch_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_pixel_office_dispatch_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_template_switching_parity_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_control_tower_parity_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "split-route control tower proof")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "GET /template-packages")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "GET /template-bindings")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "GET /bases")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "POST /migration/preview")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "pixel_office_dispatch_retirement_evidence_v1")
            and file_contains("scripts/local_brief_prepared_action_smoke.py", "local_brief_prepared_action_v1")
            and file_contains("scripts/nextjs_local_brief_smoke.py", "nextjs_local_brief_v1")
            and file_contains("scripts/nextjs_local_brief_smoke.py", "/api/mis/workflows/local-brief")
            and file_contains("scripts/nextjs_local_brief_smoke.py", "/workspace/pixel-office/local-brief")
            and file_contains("scripts/nextjs_local_brief_smoke.py", "prepared_action_exact_resume")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_pixel_office_floor_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_local_brief_v1")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-worker/route.ts", "/workflows/customer-worker-task")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-worker/route.ts", "prepared_action_id")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-worker/route.ts", "request_hash")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "Customer worker dispatch")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "Resume approved worker")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "/workspace/dispatch/customer-worker")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-worker-job/route.ts", "/workflows/customer-worker-task/submit")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-worker-job/route.ts", "prepared_action_id")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-worker-job/route.ts", "request_hash")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "Async worker jobs")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "Resume approved job")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "Prepared worker actions")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "customer-worker-prepared-actions")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "/workspace/dispatch/customer-worker-job")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerWorkflowJobs")
            and file_contains("ui/next-app/src/lib/misServer.ts", "/workflows/jobs?limit=")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerCustomerWorkerPreparedActions")
            and file_contains("ui/next-app/src/lib/misServer.ts", "/workflows/customer-worker-prepared-actions?limit=")
            and file_contains("ui/next-app/src/lib/mis.ts", "CustomerWorkerPreparedActionListPayload")
            and file_contains("ui/next-app/src/lib/mis.ts", "resume_form")
            and file_contains("scripts/nextjs_customer_worker_dispatch_smoke.py", "nextjs_customer_worker_dispatch_v1")
            and file_contains("scripts/nextjs_customer_worker_dispatch_smoke.py", "/api/mis/workflows/customer-worker-task")
            and file_contains("scripts/nextjs_customer_worker_dispatch_smoke.py", "/workspace/dispatch/customer-worker")
            and file_contains("scripts/nextjs_customer_worker_dispatch_smoke.py", "adapter_invalid")
            and file_contains("scripts/nextjs_customer_worker_dispatch_smoke.py", "plan-evidence-manifests/:id/verify")
            and file_contains("scripts/nextjs_customer_worker_async_job_smoke.py", "nextjs_customer_worker_async_job_v1")
            and file_contains("scripts/nextjs_customer_worker_async_job_smoke.py", "/api/mis/workflows/customer-worker-task/submit")
            and file_contains("scripts/nextjs_customer_worker_async_job_smoke.py", "/workspace/dispatch/customer-worker-job")
            and file_contains("scripts/nextjs_customer_worker_async_job_smoke.py", "/api/mis/workflows/jobs/:job_id")
            and file_contains("scripts/nextjs_customer_worker_async_job_smoke.py", "adapter_invalid")
            and file_contains("scripts/nextjs_customer_worker_prepared_action_smoke.py", "nextjs_customer_worker_prepared_action_v1")
            and file_contains("scripts/nextjs_customer_worker_prepared_action_smoke.py", "/api/mis/workflows/customer-worker-prepared-actions")
            and file_contains("scripts/nextjs_customer_worker_prepared_action_smoke.py", "resume_form")
            and file_contains("scripts/nextjs_customer_worker_prepared_action_smoke.py", "prepared_action_request_hash_mismatch")
            and file_contains("scripts/nextjs_customer_worker_prepared_action_smoke.py", "prepared_action_already_consumed")
            and file_contains("scripts/nextjs_worker_stuck_release_smoke.py", "nextjs_worker_stuck_release_v1")
            and file_contains("scripts/nextjs_worker_stuck_release_smoke.py", "/api/mis/workers/tasks/release")
            and file_contains("scripts/nextjs_worker_stuck_release_smoke.py", "force_release_not_allowed_next_parity")
            and file_contains("scripts/nextjs_worker_daemon_control_smoke.py", "nextjs_worker_daemon_control_v1")
            and file_contains("scripts/nextjs_worker_daemon_control_smoke.py", "/api/mis/workers/local/start")
            and file_contains("scripts/nextjs_worker_daemon_control_smoke.py", "mock_daemon_only_next_parity")
            and file_contains("scripts/nextjs_enrollment_request_smoke.py", "nextjs_enrollment_request_v1")
            and file_contains("scripts/nextjs_enrollment_request_smoke.py", "/api/mis/agent-gateway/enrollment/request")
            and file_contains("scripts/nextjs_enrollment_request_smoke.py", "enrollment_token_issue_not_allowed_next_parity")
            and file_contains("scripts/nextjs_worker_gateway_lifecycle_guard_smoke.py", "nextjs_worker_gateway_lifecycle_guard_v1")
            and file_contains("scripts/nextjs_worker_gateway_lifecycle_guard_smoke.py", "/api/mis/agent-gateway/session/create")
            and file_contains("scripts/nextjs_worker_gateway_lifecycle_guard_smoke.py", "gateway_lifecycle_write_not_allowed_next_parity")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "nextjs_worker_console_parity_v1")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "/workspace/workers")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "/api/mis/workers/fleet")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "/api/mis/workers/fleet/hygiene")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "/api/mis/operator/execution-mode")
            and file_contains("scripts/operator_execution_mode_smoke.py", "operator_execution_mode_v1")
            and file_contains("scripts/operator_execution_mode_smoke.py", "/api/operator/execution-mode")
            and file_contains("scripts/operator_execution_mode_smoke.py", "agentops operator execution-mode")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "isGatewayLifecycleWritePath")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "safeGatewaySessionsPayload")
            and file_contains("ui/next-app/src/components/AgentsParityPage.tsx", "agent-gateway-session-hygiene")
            and file_contains("ui/next-app/src/components/WorkerConsolePage.tsx", "worker_console_read_model_parity")
            and file_contains("ui/next-app/src/components/WorkerConsolePage.tsx", "worker-console-hygiene-plan")
            and file_contains("ui/next-app/src/components/WorkerConsolePage.tsx", "operator-execution-mode-readback")
            and file_contains("ui/next-app/src/components/WorkerConsolePage.tsx", "worker-console-coverage-boundary")
            and file_contains("ui/next-app/src/components/WorkerConsolePage.tsx", "Agent Gateway CLI/API/MCP canonical for token issue/rotate/revoke")
            and file_contains("ui/next-app/src/components/WorkerConsolePage.tsx", "live daemon lifecycle requires CLI/API operator lane")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "Worker Console coverage boundary")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "Agent Gateway CLI/API/MCP canonical for token issue/rotate/revoke")
            and file_contains("server.py", "def operator_execution_mode")
            and file_contains("server.py", "/api/operator/execution-mode")
            and file_contains("agentops_mis_cli/agentops.py", "operator_execution_mode")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerWorkerFleet")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerWorkerFleetHygiene")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerOperatorExecutionMode")
            and file_contains("ui/next-app/src/lib/misServer.ts", "safeGatewaySessionsPayload")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_dispatch_once_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_pixel_office_floor_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_local_brief_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_customer_worker_dispatch_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_customer_worker_async_job_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_stuck_release_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_daemon_control_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_enrollment_request_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_gateway_lifecycle_guard_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_console_parity_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "operator_execution_mode_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "Worker Console coverage boundary")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "Agent Gateway CLI/API/MCP remains canonical")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "verify_dispatch_template_run_success")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "/workspace/workers")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "/workspace/pixel-office")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", 'write_entitlement_fixture(entitlement_path, "pro_workspace")')
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Customer project started")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", 'counts.get("tasks") == 6')
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", 'counts.get("runs") == 6')
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", 'execution_evidence.get("agent_plans") == 6')
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", 'execution_evidence.get("verified_plan_evidence_manifests") == 5')
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "report_artifact_id")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Evidence Drilldown")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Run Detail")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Task Detail")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "leaked_secret")
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "tool-calls" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "pixel-office" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "pixel-office" / "local-brief" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "[agentId]" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "dispatch-once" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "dispatch" / "customer-task" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "dispatch" / "template-job" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "templates" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "templates" / "migration-preview" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "src" / "components" / "TemplateSwitchingPage.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "dispatch" / "customer-worker" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "dispatch" / "customer-worker-job" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "release-task" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "daemon-control" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "workers" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "src" / "components" / "WorkerConsolePage.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "enrollment-request" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "evaluations" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "connectors" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "connectors" / "trust" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "external-bases" / "notion" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "external-bases" / "notion" / "export" / "route.ts").exists()
            and (ROOT / "scripts" / "nextjs_parity_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_agent_gateway_task_proxy_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_agent_gateway_cli_worker_dogfood_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_dispatch_once_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_pixel_office_floor_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_pixel_office_dispatch_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_template_switching_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_control_tower_parity_smoke.py").exists()
            and (ROOT / "scripts" / "pixel_office_dispatch_retirement_evidence_smoke.py").exists()
            and (ROOT / "docs" / "PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json").exists()
            and (ROOT / "docs" / "PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.md").exists()
            and (ROOT / "scripts" / "local_brief_prepared_action_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_local_brief_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_customer_worker_dispatch_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_customer_worker_async_job_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_customer_worker_prepared_action_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_stuck_release_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_daemon_control_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_enrollment_request_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_gateway_lifecycle_guard_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_console_parity_smoke.py").exists()
            and (ROOT / "scripts" / "operator_execution_mode_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_playwright_snapshot_smoke.py").exists(),
            "parallel Next.js App Router track has API proxy, Gateway task-create proxy, CLI worker dogfood proof through the Next proxy, read-only Pixel Operating Map parity, split-route Control Tower parity across workspace/agents/governance/deployment, template/base switching readback for /template-packages, /template-bindings, /bases, and /migration/preview, local brief prepared-action exact resume with approval/hash/replay guards, covered split-route Worker Console parity across /workspace/agents and /workspace/workers with fleet/hygiene/readiness/session safety, mock worker/daemon controls, stuck release, approval-gated enrollment, operator execution-mode readback, and Agent Gateway CLI/API/MCP canonical lifecycle boundary, customer-worker prepared-action exact resume for Hermes/OpenClaw plus ledger-derived safe resume readback, async customer-worker prepared-action submit/resume plus mock job status readback, Agent Gateway session/enrollment lifecycle writes blocked at the Next proxy with safe session hygiene readback, workspace/storage/tool-call/evaluation/runtime-connector/Notion external-base/agent-detail data contracts, deployment storage gate, and browser snapshot smoke including an isolated Pro template dispatch that creates the six-task KB bot package, six run rows, report artifact, six Agent Plans, and five verified manifests",
        ),
        check(
            "pixel_office_dispatch_retirement_evidence_surface_exists",
            file_contains("docs/PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json", "pixel_office_dispatch_retirement_evidence_v1")
            and file_contains("docs/PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json", '"retirement_action": "not_executed"')
            and file_contains("docs/PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json", '"retirement_allowed": false')
            and file_contains("docs/PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json", "explicit_route_retirement_commit")
            and file_contains("docs/PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.md", "does not retire the Vite")
            and file_contains("scripts/pixel_office_dispatch_retirement_evidence_smoke.py", "pixel_office_dispatch_retirement_evidence_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "pixel_office_dispatch_retirement_evidence_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.md", "pixel_office_dispatch_retirement_evidence_v1")
            and (ROOT / "scripts" / "pixel_office_dispatch_retirement_evidence_smoke.py").exists(),
            "Pixel Office / Dispatch has explicit route retirement evidence while keeping Vite route retirement fail-closed",
        ),
        check(
            "nextjs_commercial_release_status_surface_exists",
            file_contains("server.py", "/api/commercial/release-status")
            and file_contains("server.py", "commercial_release_status_api_v1")
            and file_contains("server.py", "COMMERCIAL_RELEASE_PROMOTION_PACKET.json")
            and file_contains("server.py", "commercial_release_promotion_packet.py --include-external-ci-evidence")
            and file_contains("server.py", "commercial_release_external_ci_evidence")
            and file_contains("server.py", "include_external_ci_evidence")
            and file_contains("server.py", "network_called")
            and file_contains("ui/next-app/src/lib/mis.ts", "CommercialReleaseStatusPayload")
            and file_contains("ui/next-app/src/lib/mis.ts", "/commercial/release-status")
            and file_contains("ui/next-app/src/lib/mis.ts", "includeExternalCi")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerCommercialReleaseStatus")
            and file_contains("ui/next-app/src/lib/misServer.ts", "includeExternalCi")
            and file_contains("ui/next-app/app/workspace/commercial/page.tsx", "loadServerCommercialReleaseStatus")
            and file_contains("ui/next-app/app/workspace/commercial/page.tsx", "exact_head_ci")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Release promotion")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Exact-head CI")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Promotion packet")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Check exact-head CI")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Current evidence")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-release-status")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-release-promotion-preflight")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-promotion-packet")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-exact-head-ci-command")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-external-ci-readback-form")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-current-evidence-gates")
            and file_contains("scripts/commercial_release_status_api_smoke.py", "commercial_release_status_api_v1")
            and file_contains("scripts/commercial_release_promotion_packet.py", "commercial_release_promotion_packet_v1")
            and file_contains("scripts/commercial_release_promotion_packet_smoke.py", "commercial_release_promotion_packet_v1")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "commercial_release_status_api_smoke.py")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "commercial_release_promotion_packet_smoke.py")
            and file_contains("scripts/nextjs_parity_smoke.py", "commercial_release_status_api_v1")
            and file_contains("scripts/nextjs_parity_smoke.py", "commercial_release_promotion_packet_v1")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Release promotion")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PACKET.json", "commercial_release_promotion_packet_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PACKET.md", "commercial_release_promotion_packet_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "/api/commercial/release-status"),
            "Next commercial page renders read-only release promotion, exact-head CI command, promotion packet, and current-evidence blockers from the MIS API without network/live execution",
        ),
        check(
            "vite_browser_snapshot_surface_exists",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "vite_playwright_snapshot_smoke.py")
            and file_contains("ui/start-building-app/vite.config.ts", "VITE_AGENTOPS_PROXY_TARGET")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "vite_browser_snapshot_parity_v1")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "/mis-api/dashboard/metrics")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "snapshot_vite_detail_routes")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "detail_snapshots = snapshot_vite_detail_routes")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "snapshots + detail_snapshots")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", '"detail_task_id"')
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", '"detail_run_id"')
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "/admin/tasks/")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "/admin/runs/")
            and (ROOT / "scripts" / "vite_playwright_snapshot_smoke.py").exists(),
            "canonical Vite UI browser snapshot smoke covers list/detail routes and configurable MIS proxy target is present",
        ),
        check(
            "ui_api_parity_matrix_surface_exists",
            file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_api_parity_matrix_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.md", "scripts/ui_api_parity_matrix_smoke.py")
            and file_contains("scripts/ui_api_parity_matrix_smoke.py", "ui_api_parity_matrix_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "UI_API_PARITY_MATRIX")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_covered_route_retirement_packet_v1")
            and (ROOT / "scripts" / "ui_api_parity_matrix_smoke.py").exists(),
            "Gate 4 page-by-page Vite/Next route and API parity matrix is present, machine-checkable, and references covered-route retirement candidates",
        ),
        check(
            "ui_task_run_route_parity_surface_exists",
            file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_task_run_route_parity_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_task_run_route_parity_smoke.py")
            and file_contains("scripts/ui_task_run_route_parity_smoke.py", "ui_task_run_route_parity_v1")
            and file_contains("ui/next-app/src/components/LedgerPages.tsx", "/workspace/tasks/${encodeURIComponent(task.task_id)}")
            and file_contains("ui/next-app/src/components/LedgerPages.tsx", "/workspace/runs/${encodeURIComponent(run.run_id)}")
            and (ROOT / "scripts" / "ui_task_run_route_parity_smoke.py").exists(),
            "Gate 4 task/run route-level read-model parity and Next list-to-detail links are present",
        ),
        check(
            "ui_route_naming_decision_surface_exists",
            route_naming_decision_semantics_ok()
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "ui_route_naming_decision_v1")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "/admin/tasks/:id")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "/workspace/tasks/:taskId")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "/admin/runs")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "/workspace/runs")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "backward_compatible_redirect_or_alias")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.md", "ui_route_naming_decision_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_route_naming_decision_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_route_naming_decision_smoke.py")
            and file_contains("scripts/ui_route_naming_decision_smoke.py", "ui_route_naming_decision_v1")
            and (ROOT / "scripts" / "ui_route_naming_decision_smoke.py").exists(),
            "Gate 4 task/run route naming decision is recorded and remains fail-closed for legacy route retirement",
        ),
        check(
            "ui_legacy_route_alias_surface_exists",
            file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "ui_legacy_route_alias_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_legacy_route_alias_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_legacy_route_alias_smoke.py")
            and file_contains("scripts/ui_legacy_route_alias_smoke.py", "ui_legacy_route_alias_v1")
            and file_contains("ui/next-app/app/admin/tasks/[taskId]/page.tsx", "/workspace/tasks/")
            and file_contains("ui/next-app/app/admin/runs/page.tsx", "/workspace/runs")
            and file_contains("ui/next-app/app/admin/runs/[runId]/page.tsx", "/workspace/runs/")
            and (ROOT / "scripts" / "ui_legacy_route_alias_smoke.py").exists(),
            "Gate 4 Next.js legacy /admin task/run aliases redirect to /workspace targets while route retirement remains blocked",
        ),
        check(
            "ui_navigation_inventory_surface_exists",
            file_contains("docs/UI_NAVIGATION_INVENTORY.json", "ui_navigation_inventory_v1")
            and file_contains("docs/UI_NAVIGATION_INVENTORY.md", "ui_navigation_inventory_v1")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "canonical_navigation_inventory_verified")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_navigation_inventory_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_navigation_inventory_smoke.py")
            and file_contains("scripts/ui_navigation_inventory_smoke.py", "ui_navigation_inventory_v1")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", 'href: "/workspace/tasks"')
            and file_contains("ui/next-app/src/components/AppFrame.tsx", 'href: "/workspace/runs"')
            and (ROOT / "scripts" / "ui_navigation_inventory_smoke.py").exists(),
            "Gate 4 Next.js task/run primary navigation is inventoried under /workspace; /admin remains redirect-alias only",
        ),
        check(
            "ui_route_retirement_packet_surface_exists",
            file_contains("docs/UI_ROUTE_RETIREMENT_PACKET.json", "ui_route_retirement_packet_v1")
            and file_contains("docs/UI_ROUTE_RETIREMENT_PACKET.md", "ui_route_retirement_packet_v1")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "retirement_packet_prepared")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_route_retirement_packet_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_route_retirement_packet_smoke.py")
            and file_contains("scripts/ui_route_retirement_packet_smoke.py", "ui_route_retirement_packet_v1")
            and file_contains("docs/UI_ROUTE_RETIREMENT_PACKET.json", "\"retirement_action\": \"not_executed\"")
            and file_contains("docs/UI_ROUTE_RETIREMENT_PACKET.json", "\"retirement_allowed\": false")
            and (ROOT / "scripts" / "ui_route_retirement_packet_smoke.py").exists(),
            "Gate 4 task/run legacy route retirement packet is prepared but keeps route retirement fail-closed",
        ),
        check(
            "ui_covered_route_retirement_packet_surface_exists",
            file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", "ui_covered_route_retirement_packet_v1")
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", '"retirement_action": "not_executed"')
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", '"retirement_allowed": false')
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", "control_tower")
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", "worker_console")
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", "admin_deep_link_redirect_or_alias")
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", "same_path_ownership_cutover_commit")
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", "agent_gateway_cli_api_mcp_unchanged")
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.md", "does not retire any Vite route")
            and file_contains("scripts/ui_covered_route_retirement_packet_smoke.py", "ui_covered_route_retirement_packet_v1")
            and file_contains("scripts/ui_covered_route_retirement_packet_smoke.py", "covered_split_next_routes_no_admin_alias")
            and file_contains("scripts/ui_covered_route_retirement_packet_smoke.py", "covered_same_path_plus_focused_worker_console")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_covered_route_retirement_packet_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.md", "ui_covered_route_retirement_packet_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_covered_route_retirement_packet_smoke.py")
            and file_contains("scripts/nextjs_parity_smoke.py", "ui_covered_route_retirement_packet_v1")
            and (ROOT / "scripts" / "ui_covered_route_retirement_packet_smoke.py").exists(),
            "Gate 4 covered Control Tower and Worker Console route retirement candidates are documented while Vite retirement stays fail-closed",
        ),
        check(
            "commercial_release_evidence_packet_surface_exists",
            file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "release_evidence_packet_v1")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "commercial_release_evidence_packet_v1")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "deployment_readiness_smoke.py --postgres-write-fixture")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "nextjs_playwright_snapshot_smoke.py --postgres-write-fixture")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "local_runtime_acceptance.py --live-openclaw --live-hermes")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "commercial_release_evidence_packet_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "deployment_readiness_postgres_runtime_write_fixture_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "nextjs_deployment_postgres_runtime_write_fixture_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "byoc_deployment_acceptance_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "real_hermes_openclaw_acceptance")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "HERMES_ALLOW_REAL_RUN=true")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.md", "mock evidence is CI/offline fallback only")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.md", "mock-only")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "release_evidence_packet_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_release_evidence_packet_smoke.py")
            and file_contains("scripts/release_evidence_packet_smoke.py", "release_evidence_packet_v1")
            and file_contains("scripts/commercial_release_evidence_packet_smoke.py", "commercial_release_evidence_packet_v1")
            and file_contains("scripts/commercial_release_evidence_packet_smoke.py", "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture")
            and (ROOT / "scripts" / "release_evidence_packet_smoke.py").exists()
            and (ROOT / "scripts" / "commercial_release_evidence_packet_smoke.py").exists(),
            "Commercial release evidence packet makes Gate 5 BYOC/Postgres and real Hermes/OpenClaw evidence machine-checkable",
        ),
        check(
            "commercial_handoff_status_surface_exists",
            file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_handoff_status_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_evidence_receipts_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_current_evidence_status_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_release_evidence_packet_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "release_evidence_packet_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "release_freeze_protocol_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "merge_readiness_status_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "phase_gate_statuses")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "current_evidence_status")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "gates_with_local_receipts")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "explicit_blockers")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "required_commands")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "python3 scripts/commercial_evidence_receipts.py")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "python3 scripts/commercial_evidence_receipts_smoke.py")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "python3 scripts/commercial_current_evidence_status.py")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "python3 scripts/commercial_current_evidence_status_smoke.py")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "python3 scripts/commercial_handoff_status.py")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "python3 scripts/commercial_handoff_status_smoke.py")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.md", "blocked_release_evidence_required")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "commercial_handoff_status_smoke.py")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "handoff_status_command")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "current_evidence_status_command")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_handoff_status_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_handoff_status_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_handoff_status_v1")
            and file_contains("scripts/commercial_handoff_status.py", "commercial_handoff_status_v1")
            and file_contains("scripts/commercial_handoff_status.py", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_handoff_status.py", "--require-handoff-ready")
            and file_contains("scripts/commercial_handoff_status_smoke.py", "commercial_handoff_status_v1")
            and file_contains("scripts/commercial_handoff_status_smoke.py", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_handoff_status_smoke.py", "phase_gate_statuses")
            and (ROOT / "scripts" / "commercial_handoff_status.py").exists()
            and (ROOT / "scripts" / "commercial_handoff_status_smoke.py").exists(),
            "Commercial handoff status gives operators one CI-safe command for current gate states, blockers, and required evidence",
        ),
        check(
            "commercial_evidence_receipts_surface_exists",
            file_contains("docs/COMMERCIAL_EVIDENCE_RECEIPTS.json", "commercial_evidence_receipts_v1")
            and file_contains("docs/COMMERCIAL_EVIDENCE_RECEIPTS.json", "partial_local_receipts_not_release_complete")
            and file_contains("docs/COMMERCIAL_EVIDENCE_RECEIPTS.json", "local_receipts_complete_exact_head_required")
            and file_contains("docs/COMMERCIAL_EVIDENCE_RECEIPTS.json", "gate_5_byoc_enterprise_deployment")
            and file_contains("docs/COMMERCIAL_EVIDENCE_RECEIPTS.md", "commercial_evidence_receipts_v1")
            and file_contains("docs/COMMERCIAL_EVIDENCE_RECEIPTS.md", "commercial_evidence_receipts_smoke.py")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "gates_with_local_receipts")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "release_grade_current")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "gates_with_local_receipts")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "evidence_receipts_contract_id")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_evidence_receipts_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_evidence_receipts_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_evidence_receipts.py", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_evidence_receipts.py", "--require-release-grade")
            and file_contains("scripts/commercial_evidence_receipts_smoke.py", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_evidence_receipts_smoke.py", "release_grade_current")
            and (ROOT / "scripts" / "commercial_evidence_receipts.py").exists()
            and (ROOT / "scripts" / "commercial_evidence_receipts_smoke.py").exists(),
            "Commercial evidence receipts record local hash/ref-only Gate 5 evidence while keeping release-grade, handoff, and merge states false",
        ),
        check(
            "commercial_current_evidence_status_surface_exists",
            file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "commercial_current_evidence_status_v1")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "commercial_evidence_receipts_v1")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "current_evidence_required")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "phase_gate_evidence_statuses")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "gates_requiring_current_evidence")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "gates_with_local_receipts")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "local_receipt_current")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "release_grade_current")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "heavy_evidence_not_executed_by_default")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "gate_5_byoc_enterprise_deployment")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md", "commercial_current_evidence_status_v1")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md", "commercial_evidence_receipts_v1")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md", "commercial_evidence_receipts_smoke.py")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md", "commercial_current_evidence_status_smoke.py")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "commercial_current_evidence_status_smoke.py")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "current_evidence_status_contract_id")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_current_evidence_status_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_current_evidence_status_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_current_evidence_status_v1")
            and file_contains("scripts/commercial_current_evidence_status.py", "commercial_current_evidence_status_v1")
            and file_contains("scripts/commercial_current_evidence_status.py", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_current_evidence_status.py", "local_receipt_current")
            and file_contains("scripts/commercial_current_evidence_status.py", "--require-current-evidence")
            and file_contains("scripts/commercial_current_evidence_status_smoke.py", "commercial_current_evidence_status_v1")
            and file_contains("scripts/commercial_current_evidence_status_smoke.py", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_current_evidence_status_smoke.py", "gates_requiring_current_evidence")
            and (ROOT / "scripts" / "commercial_current_evidence_status.py").exists()
            and (ROOT / "scripts" / "commercial_current_evidence_status_smoke.py").exists(),
            "Commercial current evidence status makes per-gate evidence freshness gaps machine-readable without executing heavy/live checks",
        ),
        check(
            "commercial_exact_head_ci_evidence_surface_exists",
            file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json", "commercial_exact_head_ci_evidence_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.md", "commercial_exact_head_ci_evidence.py --from-gh --require-current-head")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_exact_head_ci_evidence.py --from-gh --require-current-head")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_exact_head_ci_evidence_v1")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_exact_head_ci_evidence_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_exact_head_ci_evidence_v1")
            and file_contains("scripts/commercial_exact_head_ci_evidence.py", "commercial_exact_head_ci_evidence_v1")
            and file_contains("scripts/commercial_exact_head_ci_evidence.py", "--require-current-head")
            and file_contains("scripts/commercial_exact_head_ci_evidence_smoke.py", "commercial_exact_head_ci_evidence_v1")
            and (ROOT / "scripts" / "commercial_exact_head_ci_evidence.py").exists()
            and (ROOT / "scripts" / "commercial_exact_head_ci_evidence_smoke.py").exists(),
            "Commercial exact-head CI evidence reader makes current-head GitHub Actions proof external to committed receipts",
        ),
        check(
            "commercial_release_promotion_preflight_surface_exists",
            file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json", "blocked_release_promotion_required")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json", "commercial_exact_head_ci_evidence_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json", "release_promotion_allowed")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json", "release_grade_update_allowed")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.md", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.md", "--include-external-ci-evidence --require-promotion-ready")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_release_promotion_preflight_v1")
            and file_contains("scripts/commercial_release_promotion_preflight.py", "commercial_release_promotion_preflight_v1")
            and file_contains("scripts/commercial_release_promotion_preflight.py", "--include-external-ci-evidence")
            and file_contains("scripts/commercial_release_promotion_preflight_smoke.py", "commercial_release_promotion_preflight_v1")
            and file_contains("scripts/commercial_release_promotion_preflight_smoke.py", "release_grade_receipts_empty")
            and (ROOT / "scripts" / "commercial_release_promotion_preflight.py").exists()
            and (ROOT / "scripts" / "commercial_release_promotion_preflight_smoke.py").exists(),
            "Commercial release promotion preflight makes exact-head CI, remote sync, clean worktree, and release-grade receipt blockers machine-readable",
        ),
        check(
            "release_freeze_protocol_surface_exists",
            file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "release_freeze_protocol_v1")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "freeze_active_not_release_complete")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_release_evidence_packet_v1")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "nextjs_playwright_snapshot_smoke.py --postgres-write-fixture")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "local_runtime_acceptance.py --live-openclaw --live-hermes")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "sqlite_fallback_as_postgres_proof")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.md", "freeze_active_not_release_complete")
            and file_contains("scripts/release_freeze_protocol_smoke.py", "release_freeze_protocol_v1")
            and file_contains("scripts/release_freeze_protocol_smoke.py", "freeze_active_not_release_complete")
            and file_contains("scripts/release_freeze_protocol_smoke.py", "release_evidence_packet_smoke.py")
            and (ROOT / "scripts" / "release_freeze_protocol_smoke.py").exists(),
            "Release freeze protocol keeps commercial handoff frozen until Gate 5 Postgres/BYOC and real runtime evidence are current",
        ),
        check(
            "merge_readiness_status_surface_exists",
            file_contains("docs/MERGE_READINESS_STATUS.json", "merge_readiness_status_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "blocked_release_evidence_required")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", '"merge_allowed": false')
            and file_contains("docs/MERGE_READINESS_STATUS.json", '"commercial_handoff_allowed": false')
            and file_contains("docs/MERGE_READINESS_STATUS.json", "release_freeze_protocol_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_release_evidence_packet_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "local_runtime_acceptance.py --live-openclaw --live-hermes")
            and file_contains("docs/MERGE_READINESS_STATUS.md", "blocked_release_evidence_required")
            and file_contains("scripts/merge_readiness_status_smoke.py", "merge_readiness_status_v1")
            and file_contains("scripts/merge_readiness_status_smoke.py", "blocked_release_evidence_required")
            and file_contains("scripts/merge_readiness_status_smoke.py", "release_freeze_protocol_smoke.py")
            and (ROOT / "scripts" / "merge_readiness_status_smoke.py").exists(),
            "Merge readiness remains explicitly blocked until release, freeze, Gate 5 BYOC/Postgres, and real runtime evidence are current",
        ),
        check(
            "postgres_is_gated_not_immediate",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "Storage Boundary Before Postgres"),
            "Postgres migration is behind a storage-boundary gate",
        ),
        check(
            "storage_boundary_surface_exists",
            file_contains("docs/STORAGE_BOUNDARY_MAP.md", "repo_list_workspace_tasks")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_parity_pre_container_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_container_parity_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_adapter_sql_contract_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_optional_psycopg_adapter_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "LIKE '%...%'")
            and file_contains("scripts/storage_postgres_optional_adapter_smoke.py", "literal_percent_like")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_boundary_fixture_parity_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_route_read_model_parity_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "storage_backend_selection_fail_closed_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_http_read_parity_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "storage_postgres_http_read_parity_smoke.py")
            and file_contains("server.py", "repo_list_workspace_tasks")
            and file_contains("server.py", "storage_backend_status")
            and file_contains("server.py", "postgres_read_only_backend")
            and (ROOT / "agentops_mis_storage" / "postgres.py").exists()
            and (ROOT / "agentops_mis_storage" / "parity_fixture.py").exists()
            and (ROOT / "scripts" / "storage_boundary_sqlite_smoke.py").exists()
            and (ROOT / "scripts" / "storage_postgres_boundary_parity_smoke.py").exists()
            and (ROOT / "scripts" / "storage_postgres_route_read_model_smoke.py").exists()
            and (ROOT / "scripts" / "storage_postgres_http_read_parity_smoke.py").exists()
            and (ROOT / "scripts" / "storage_backend_selection_smoke.py").exists(),
            "workspace-scoped helpers, isolated SQLite smoke, Postgres container parity, adapter SQL contract, optional psycopg adapter, shared boundary fixture parity, route read-model parity, fail-closed backend selection, and read-only Postgres HTTP parity are present",
        ),
        check(
            "postgres_cli_read_parity_surface_exists",
            file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_cli_read_parity_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "storage_postgres_cli_read_parity_smoke.py")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "storage_postgres_cli_read_parity_smoke.py")
            and file_contains("docs/AGENT_GATEWAY_CLI_SPEC.md", "storage_postgres_cli_read_parity_smoke.py")
            and file_contains("scripts/storage_postgres_cli_read_parity_smoke.py", "agent_plan_verify")
            and file_contains("scripts/storage_postgres_cli_read_parity_smoke.py", "plan_evidence_verify")
            and (ROOT / "scripts" / "storage_postgres_cli_read_parity_smoke.py").exists(),
            "read-only Postgres CLI/API parity smoke and docs include Agent Plan and plan-evidence reads",
        ),
        check(
            "postgres_write_helper_parity_surface_exists",
            file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_write_helper_parity_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "storage_postgres_write_helper_parity_smoke.py")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "storage_postgres_write_helper_parity_smoke.py")
            and file_contains("agentops_mis_storage/postgres.py", "translate_sqlite_insert_or_ignore")
            and file_contains("server.py", 'previous["tamper_chain_hash"]')
            and (ROOT / "scripts" / "storage_postgres_write_helper_parity_smoke.py").exists(),
            "Postgres write-helper parity smoke, INSERT OR IGNORE translation, and audit dict-row compatibility are present",
        ),
        check(
            "postgres_http_write_task_surface_exists",
            file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_http_write_task_parity_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "storage_postgres_http_write_task_smoke.py")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "storage_postgres_http_write_task_smoke.py")
            and file_contains("docs/AGENT_GATEWAY_CLI_SPEC.md", "Postgres routed task/execution/heartbeat/evidence/plan/memory/approval/audit helper")
            and file_contains("server.py", "AGENTOPS_POSTGRES_WRITE_HTTP")
            and file_contains("server.py", "POSTGRES_HTTP_WRITE_ALLOWED_ROUTES")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", 'method="POST"')
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/tasks")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/tasks")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/tasks/{GATEWAY_TASK_ID}/claim")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/runs/start")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/tool-calls")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/artifacts")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/evaluations/submit")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/agent-plans")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/plan-evidence-manifests")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/memories/propose")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/approvals/request")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/audit")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/integrations/openclaw/probe")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/integrations/hermes/run-task")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_openclaw_prepare_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_openclaw_approve_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_openclaw_resume_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_openclaw_replay_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_hermes_prepare_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_hermes_approve_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_hermes_resume_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_hermes_replay_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_non_prepared_approval_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_claim_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_run_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_tool_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_eval_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_artifact_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_plan_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_manifest_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_memory_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_approval_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_audit_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_plan_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_header_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_header_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_audit_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_heartbeat_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_header_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_other_agent_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_claim_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_run_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_tool_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_eval_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_artifact_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_plan_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_manifest_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_memory_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_approval_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_audit_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_audit_no_run_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_heartbeat_intruder_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_intruder_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_heartbeat_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_plan_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_audit_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_manifest_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_approved_overwrite_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_existing_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_other_agent_overwrite_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_tool_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_approved_overwrite_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_other_agent_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_task_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_terminal_revival_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_completion_heartbeat_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_audit_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_non_allowlisted_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_execution_start_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_evidence_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_plan_evidence_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_approval_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_audit_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_memory_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_heartbeat_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_run_heartbeat_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_run_completion_heartbeat_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_runtime_prepared_action_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_runtime_approval_decision_write_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_http_gateway_run_completion_heartbeat_write_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_http_runtime_prepared_action_write_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "fixed Hermes/OpenClaw prepare")
            and file_contains("docs/AGENT_GATEWAY_CLI_SPEC.md", "complete a running run through heartbeat")
            and file_contains("server.py", '("POST", "/api/agent-gateway/tool-calls")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/artifacts")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/evaluations/submit")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/heartbeat")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/runs/:run_id/heartbeat")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/agent-plans")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/plan-evidence-manifests")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/memories/propose")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/approvals/request")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/audit")')
            and file_contains("server.py", '("POST", "/api/integrations/openclaw/probe")')
            and file_contains("server.py", '("POST", "/api/integrations/hermes/run-task")')
            and file_contains("server.py", '("POST", "/api/approvals/:approval_id/approve")')
            and file_contains("server.py", "POSTGRES_HTTP_PREPARED_ACTION_DECISION_TYPES")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_heartbeat_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_completion_heartbeat_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_run_id")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_task_id")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_agent_id")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_run_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_task_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_agent_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_run_ended")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_tool_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_eval_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_artifact_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_plan_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_manifest_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_manifest_verification_pass")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_audit_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_tool_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_eval_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_artifact_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_plan_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_manifest_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_audit_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_audit_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_run_wait_audit_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_task_wait_audit_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_heartbeat_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_completion_heartbeat_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_completion_heartbeat_audit_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_token_last_heartbeat")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_audit_runtime_event_count")
            and (ROOT / "scripts" / "storage_postgres_http_write_task_smoke.py").exists(),
            "experimental Postgres HTTP task, Agent Gateway task, claim, run-start, agent/run progress and completion heartbeat, tool/eval/artifact evidence, Agent Plan, plan-evidence manifest, memory candidate, approval request, and run-bound audit write routes are explicitly allowlisted, smoke-tested, and documented",
        ),
        check(
            "postgres_cli_write_parity_surface_exists",
            file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_cli_write_parity_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "storage_postgres_cli_write_parity_smoke.py")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "storage_postgres_cli_write_parity_smoke.py")
            and file_contains("docs/AGENT_GATEWAY_CLI_SPEC.md", "Postgres CLI write parity helper")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "postgres_cli_write_parity_v1")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "run_cli(")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "http_write.server_env")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "agent_heartbeat")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "task_create")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "task_claim")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "run_start")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "run_heartbeat")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "toolcall_record")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "evaluation_submit")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "artifact_record")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "agent_plan_create")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "plan_evidence_create")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "memory_propose")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "approval_request")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "audit_emit")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "run_completion_heartbeat")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "cli_read_only_task_status")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "cli_missing_scope_status")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "cli_non_allowlisted_write_status")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "postgres_cli_gateway_run_completion_heartbeat_write_v1")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "gateway_manifest_status")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "gateway_token_last_heartbeat")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "gateway_run_completion_heartbeat_audit_count")
            and (ROOT / "scripts" / "storage_postgres_cli_write_parity_smoke.py").exists(),
            "Postgres-backed Agent Gateway CLI/API write parity smoke uses actual agentops commands for scoped task, run, heartbeat, evidence, Agent Plan, plan-evidence, memory, approval, audit, and completion heartbeat writes while checking fail-closed CLI guards",
        ),
        check(
            "byoc_deployment_acceptance_surface_exists",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "byoc_deployment_acceptance_v1")
            and file_contains("docs/CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md", "agentops_signed_audit_export.py")
            and file_contains("docs/CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md", "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "byoc_deployment_acceptance_v1")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "--postgres-readiness-fixture")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "deployment_readiness_postgres_runtime_write_fixture_v1")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "runtime_write_gate_status")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "experimental_write_http")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "postgres_read_only_backend")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "postgres_counts_unchanged")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "signed_audit_export")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "tamper_detected")
            and file_contains("scripts/agentops_signed_audit_export.py", "signed_audit_export_v1")
            and file_contains("scripts/agentops_signed_audit_export.py", "signing_key_required")
            and file_contains("scripts/local_readiness_smoke.py", "byoc_deployment_acceptance_smoke")
            and file_contains("server.py", "deployment_checks")
            and file_contains("server.py", "signed_export_tamper_detection")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "Recovery drill")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "Signed export")
            and file_contains("ui/next-app/README.md", "deployment_readiness_smoke.py --postgres-write-fixture")
            and file_contains("ui/next-app/README.md", "nextjs_playwright_snapshot_smoke.py --postgres-write-fixture")
            and (ROOT / "scripts" / "agentops_signed_audit_export.py").exists()
            and (ROOT / "scripts" / "byoc_deployment_acceptance_smoke.py").exists(),
            "Gate 5 BYOC deployment acceptance covers backup/restore confirmation, pre-restore safety copy, signed audit export key requirement, tamper detection, raw metadata omission, Postgres runtime write-gate readiness, and Next.js deployment readiness",
        ),
        check(
            "deployment_readiness_surface_exists",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "deployment_readiness_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "enterprise_byoc_controls_v1")
            and file_contains("server.py", "def deployment_readiness")
            and file_contains("server.py", "def enterprise_byoc_controls")
            and file_contains("server.py", "/api/deployment/readiness")
            and file_contains("server.py", "/api/deployment/enterprise-controls")
            and file_contains("server.py", "AGENTOPS_ENTERPRISE_CONTROLS_PATH")
            and file_contains("agentops_mis_cli/agentops.py", "cmd_deployment_readiness")
            and file_contains("agentops_mis_cli/agentops.py", "cmd_deployment_enterprise_controls")
            and file_contains("agentops_mis_cli/agentops.py", 'sub.add_parser("deployment"')
            and file_contains("scripts/deployment_readiness_smoke.py", "deployment_readiness_v1")
            and file_contains("scripts/deployment_readiness_smoke.py", "enterprise_byoc_controls_v1")
            and file_contains("scripts/deployment_readiness_smoke.py", "audit_retention_policy_v1")
            and file_contains("scripts/deployment_readiness_smoke.py", "audit_retention_controls_v1")
            and file_contains("scripts/deployment_readiness_smoke.py", "--configured-retention-fixture")
            and file_contains("scripts/deployment_readiness_smoke.py", "--configured-enterprise-fixture")
            and file_contains("scripts/deployment_readiness_smoke.py", "--postgres-write-fixture")
            and file_contains("scripts/deployment_readiness_smoke.py", "deployment_readiness_postgres_runtime_write_fixture_v1")
            and file_contains("scripts/deployment_readiness_smoke.py", "validate_postgres_write_readiness")
            and file_contains("scripts/deployment_readiness_smoke.py", "runtime_write_gate")
            and file_contains("scripts/deployment_readiness_smoke.py", "POST /api/integrations/openclaw/probe")
            and file_contains("scripts/deployment_readiness_smoke.py", "POST /api/integrations/hermes/run-task")
            and file_contains("scripts/deployment_readiness_smoke.py", "POST /api/approvals/:approval_id/approve")
            and file_contains("docs/CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md", "deployment_readiness_smoke.py --postgres-write-fixture")
            and file_contains("ui/next-app/README.md", "fixed Postgres runtime write-gate readiness")
            and file_contains("scripts/deployment_readiness_smoke.py", "validate_configured_retention")
            and file_contains("scripts/deployment_readiness_smoke.py", "validate_configured_enterprise")
            and file_contains("scripts/deployment_readiness_smoke.py", "AGENTOPS_RETENTION_CONTROLS_PATH")
            and file_contains("scripts/deployment_readiness_smoke.py", "pro_workspace")
            and file_contains("scripts/deployment_readiness_smoke.py", "enterprise_byoc")
            and file_contains("scripts/deployment_readiness_smoke.py", "write_enterprise_controls_fixture")
            and file_contains("scripts/deployment_readiness_smoke.py", "sso_connector_policy")
            and file_contains("scripts/deployment_readiness_smoke.py", "custom_connector_sdk")
            and file_contains("scripts/deployment_readiness_smoke.py", "private_connector_total")
            and file_contains("scripts/deployment_readiness_smoke.py", "raw-private-connector-token")
            and file_contains("scripts/deployment_readiness_smoke.py", "legal_hold_registry_configured")
            and file_contains("scripts/deployment_readiness_smoke.py", "active_legal_holds")
            and file_contains("scripts/deployment_readiness_smoke.py", "cleanup_approval_required")
            and file_contains("scripts/deployment_readiness_smoke.py", "legal_hold_required_before_cleanup")
            and file_contains("scripts/deployment_readiness_smoke.py", "cleanup_endpoint_exposed")
            and file_contains("scripts/deployment_readiness_smoke.py", "destructive_cleanup_supported")
            and file_contains("scripts/deployment_readiness_smoke.py", "db_dump_hash")
            and file_contains("scripts/deployment_readiness_smoke.py", "agentops-deployment")
            and file_contains("scripts/audit_retention_policy_smoke.py", "audit_retention_policy_v1")
            and file_contains("scripts/audit_retention_policy_smoke.py", "delete_performed")
            and file_contains("scripts/audit_retention_policy_smoke.py", "db_dump_hash")
            and file_contains("scripts/audit_retention_controls_smoke.py", "audit_retention_controls_v1")
            and file_contains("scripts/audit_retention_controls_smoke.py", "cleanup_approval_required")
            and file_contains("scripts/audit_retention_controls_smoke.py", "--configured-fixture")
            and file_contains("scripts/audit_retention_controls_smoke.py", "validate_configured_registry")
            and file_contains("scripts/audit_retention_controls_smoke.py", "cannot_assert_no_holds")
            and file_contains("scripts/audit_retention_controls_smoke.py", "Highly confidential subject")
            and file_contains("config/retention-controls.example.json", '"legal_hold_registry_configured": true')
            and file_contains("config/retention-controls.example.json", '"legal_holds"')
            and file_contains("config/retention-controls.example.json", '"status": "active"')
            and file_contains("config/enterprise-controls.example.json", '"registry_configured": true')
            and file_contains("config/enterprise-controls.example.json", '"trust_policy_configured": true')
            and file_contains("scripts/audit_retention_controls_smoke.py", "db_dump_hash")
            and file_contains("server.py", "def audit_retention_policy")
            and file_contains("server.py", "def audit_retention_controls")
            and file_contains("server.py", "/api/audit/retention-policy")
            and file_contains("server.py", "/api/audit/retention-controls")
            and file_contains("agentops_mis_cli/agentops.py", "cmd_audit_retention_policy")
            and file_contains("agentops_mis_cli/agentops.py", "cmd_audit_retention_controls")
            and file_contains("scripts/nextjs_parity_smoke.py", "loadServerDeploymentReadiness")
            and file_contains("ui/next-app/src/lib/misServer.ts", "/deployment/readiness")
            and file_contains("ui/next-app/src/lib/misServer.ts", "/deployment/enterprise-controls")
            and file_contains("ui/next-app/src/lib/misServer.ts", "/audit/retention-policy")
            and file_contains("ui/next-app/src/lib/misServer.ts", "/audit/retention-controls")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "Deployment readiness verdict")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "audit_retention_policy_v1")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "audit_retention_controls_v1")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "private connectors")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "verify_deployment_configured_retention")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "deployment_configured_retention_controls")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "--configured-retention-fixture")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "nextjs_deployment_configured_retention_fixture_v1")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "--postgres-write-fixture")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "nextjs_deployment_postgres_runtime_write_fixture_v1")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "verify_deployment_postgres_write_gate")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "runtime_write_gate")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "POST /api/integrations/openclaw/probe")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "POST /api/integrations/hermes/run-task")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "POST /api/approvals/:approval_id/approve")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "enterprise_byoc_controls_v1")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "enterprise_byoc")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "sso_connector_policy")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "connector sdk true")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "private connectors 1/2")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "AGENTOPS_RETENTION_CONTROLS_PATH")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "AGENTOPS_ENTERPRISE_CONTROLS_PATH")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "active_legal_holds")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "cleanup_endpoint_exposed")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "destructive_cleanup_supported")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "retention-controls?cleanup=true")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "dangerous_cleanup_parameter_rejected")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Raw Next deployment legal hold reason")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "db_dump_hash")
            and (ROOT / "scripts" / "deployment_readiness_smoke.py").exists(),
            "Gate 5 deployment readiness API, CLI, smoke, audit retention policy/controls previews, configured Enterprise SSO/private connector proof, and configured Next.js verdict panel are present",
        ),
        check(
            "blocked_generated_or_runtime_artifacts_absent",
            not blocked_paths,
            "blocked_paths=" + json.dumps(blocked_paths, ensure_ascii=False),
            "git status --short",
        ),
    ]

    gates = [
        {
            "id": "gate_0",
            "name": "Isolated Commercial Track",
            "status": "ready" if checks[0]["ok"] and checks[1]["ok"] and checks[-1]["ok"] else "blocked",
            "verify": ["python3 scripts/commercial_migration_readiness.py", "git diff --check"],
        },
        {
            "id": "gate_1",
            "name": "Product Packaging and Entitlement",
            "status": "next",
            "verify": ["entitlement smoke test", "token omission check"],
        },
        {
            "id": "gate_2",
            "name": "Production Safety Baseline",
            "status": "next",
            "verify": [
                "python3 scripts/production_auth_fail_closed_smoke.py --configured-production-fixture",
                "python3 scripts/security_production_readiness_smoke.py --configured-production-fixture",
                "python3 scripts/agent_gateway_scope_matrix_smoke.py --isolated-fixture",
                "python3 scripts/workspace_isolation_smoke.py --isolated-fixture",
                "python3 scripts/workspace_rbac_governance_smoke.py --isolated-fixture",
                "python3 scripts/workspace_memory_session_governance_smoke.py --isolated-fixture",
            ],
        },
        {
            "id": "gate_3",
            "name": "Storage Boundary Before Postgres",
            "status": "next",
            "verify": [
                "python3 scripts/storage_boundary_sqlite_smoke.py",
                "python3 scripts/storage_postgres_contract_smoke.py",
                "python3 scripts/storage_postgres_container_smoke.py",
                "python3 scripts/storage_postgres_adapter_contract_smoke.py",
                "python3 scripts/storage_postgres_optional_adapter_smoke.py",
                "python3 scripts/storage_postgres_boundary_parity_smoke.py",
                "python3 scripts/storage_postgres_route_read_model_smoke.py",
                "python3 scripts/storage_backend_selection_smoke.py",
                "python3 scripts/storage_postgres_http_read_parity_smoke.py",
                "python3 scripts/storage_postgres_cli_read_parity_smoke.py",
                "python3 scripts/storage_postgres_write_helper_parity_smoke.py",
                "python3 scripts/storage_postgres_http_write_task_smoke.py",
                "python3 scripts/storage_postgres_cli_write_parity_smoke.py",
            ],
        },
        {
            "id": "gate_4",
            "name": "UI/API Parity Before Next.js",
            "status": "started",
            "verify": [
                "python3 scripts/nextjs_parity_smoke.py",
                "python3 scripts/commercial_evidence_receipts_smoke.py",
                "python3 scripts/commercial_current_evidence_status_smoke.py",
                "python3 scripts/commercial_handoff_status_smoke.py",
                "python3 scripts/release_evidence_packet_smoke.py",
                "python3 scripts/commercial_release_evidence_packet_smoke.py",
                "python3 scripts/release_freeze_protocol_smoke.py",
                "python3 scripts/merge_readiness_status_smoke.py",
                "cd ui/start-building-app && npm run build",
                "cd ui/next-app && npm run build",
                "python3 scripts/ui_api_parity_matrix_smoke.py",
                "python3 scripts/ui_task_run_route_parity_smoke.py",
                "python3 scripts/ui_route_naming_decision_smoke.py",
                "python3 scripts/ui_legacy_route_alias_smoke.py",
                "python3 scripts/ui_navigation_inventory_smoke.py",
                "python3 scripts/ui_route_retirement_packet_smoke.py",
                "python3 scripts/ui_covered_route_retirement_packet_smoke.py",
                "python3 scripts/pixel_office_dispatch_retirement_evidence_smoke.py",
                "python3 scripts/nextjs_agent_gateway_task_proxy_smoke.py",
                "python3 scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py",
                "python3 scripts/nextjs_worker_dispatch_once_smoke.py",
                "python3 scripts/nextjs_pixel_office_floor_smoke.py",
                "python3 scripts/nextjs_pixel_office_dispatch_smoke.py",
                "python3 scripts/nextjs_control_tower_parity_smoke.py",
                "python3 scripts/nextjs_template_switching_smoke.py",
                "python3 scripts/local_brief_prepared_action_smoke.py",
                "python3 scripts/nextjs_local_brief_smoke.py",
                "python3 scripts/nextjs_customer_worker_dispatch_smoke.py",
                "python3 scripts/nextjs_customer_worker_async_job_smoke.py",
                "python3 scripts/nextjs_customer_worker_prepared_action_smoke.py",
                "python3 scripts/nextjs_worker_stuck_release_smoke.py",
                "python3 scripts/nextjs_worker_daemon_control_smoke.py",
                "python3 scripts/nextjs_enrollment_request_smoke.py",
                "python3 scripts/nextjs_worker_gateway_lifecycle_guard_smoke.py",
                "python3 scripts/nextjs_worker_console_parity_smoke.py",
                "python3 scripts/operator_execution_mode_smoke.py",
                "python3 scripts/vite_playwright_snapshot_smoke.py",
                "python3 scripts/nextjs_playwright_snapshot_smoke.py",
            ],
        },
        {
            "id": "gate_5",
            "name": "BYOC / Enterprise Deployment",
            "status": "planned",
            "verify": [
                "Postgres container parity smoke",
                "Postgres ledger acceptance",
                "python3 scripts/commercial_evidence_receipts_smoke.py",
                "python3 scripts/commercial_current_evidence_status_smoke.py",
                "python3 scripts/commercial_handoff_status_smoke.py",
                "python3 scripts/release_evidence_packet_smoke.py",
                "python3 scripts/commercial_release_evidence_packet_smoke.py",
                "python3 scripts/release_freeze_protocol_smoke.py",
                "python3 scripts/merge_readiness_status_smoke.py",
                "python3 scripts/audit_retention_policy_smoke.py",
                "python3 scripts/audit_retention_controls_smoke.py --configured-fixture",
                "python3 scripts/deployment_readiness_smoke.py --configured-retention-fixture --configured-enterprise-fixture",
                "python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture",
                "python3 scripts/nextjs_playwright_snapshot_smoke.py --configured-retention-fixture",
                "python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture",
                "python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
                "backup/restore and signed export checks",
            ],
        },
    ]

    overall_ready = all(item["ok"] for item in checks)
    payload = {
        "overall_status": "ready" if overall_ready else "blocked",
        "branch": branch,
        "worktree": str(ROOT),
        "strategy": {
            "rewrite_policy": "no_big_bang",
            "backend": "keep_python_control_plane_until_api_parity_and_production_safety_pass",
            "database": "sqlite_first_postgres_after_storage_boundary",
            "frontend": "vite_react_canonical_nextjs_parallel_parity_started",
            "agent_contract": "agent_gateway_cli_api_mcp_remains_durable",
        },
        "checks": checks,
        "phase_gates": gates,
        "pending_paths": paths,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if overall_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
