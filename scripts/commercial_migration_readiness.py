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
        "docs/UI_ROUTE_NAMING_DECISION.md",
        "docs/UI_ROUTE_NAMING_DECISION.json",
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
            and file_contains("agentops_mis_cli/agentops.py", "production-readiness"),
            "server API and CLI production-readiness command are present",
        ),
        check(
            "entitlement_direction_recorded",
            file_contains("docs/PRICING_AND_ENTITLEMENT_DRAFT.md", "Enterprise / BYOC")
            and file_contains("docs/PRICING_AND_ENTITLEMENT_DRAFT.md", "Free Local"),
            "edition ladder exists in pricing/entitlement draft",
        ),
        check(
            "entitlement_status_surface_exists",
            file_contains("server.py", "/api/commercial/entitlements")
            and file_contains("agentops_mis_cli/agentops.py", "commercial_entitlements")
            and (ROOT / "scripts" / "commercial_entitlements_smoke.py").exists(),
            "read-only commercial entitlement API, CLI, and smoke test are present",
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
            and file_contains("scripts/nextjs_worker_stuck_release_smoke.py", "nextjs_worker_stuck_release_v1")
            and file_contains("scripts/nextjs_worker_stuck_release_smoke.py", "/api/mis/workers/tasks/release")
            and file_contains("scripts/nextjs_worker_stuck_release_smoke.py", "force_release_not_allowed_next_parity")
            and file_contains("scripts/nextjs_worker_daemon_control_smoke.py", "nextjs_worker_daemon_control_v1")
            and file_contains("scripts/nextjs_worker_daemon_control_smoke.py", "/api/mis/workers/local/start")
            and file_contains("scripts/nextjs_worker_daemon_control_smoke.py", "mock_daemon_only_next_parity")
            and file_contains("scripts/nextjs_enrollment_request_smoke.py", "nextjs_enrollment_request_v1")
            and file_contains("scripts/nextjs_enrollment_request_smoke.py", "/api/mis/agent-gateway/enrollment/request")
            and file_contains("scripts/nextjs_enrollment_request_smoke.py", "enrollment_token_issue_not_allowed_next_parity")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_dispatch_once_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_stuck_release_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_daemon_control_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_enrollment_request_v1")
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "tool-calls" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "[agentId]" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "dispatch-once" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "release-task" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "daemon-control" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "enrollment-request" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "evaluations" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "connectors" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "connectors" / "trust" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "external-bases" / "notion" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "external-bases" / "notion" / "export" / "route.ts").exists()
            and (ROOT / "scripts" / "nextjs_parity_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_agent_gateway_task_proxy_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_dispatch_once_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_stuck_release_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_daemon_control_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_enrollment_request_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_playwright_snapshot_smoke.py").exists(),
            "parallel Next.js App Router track has API proxy, Gateway task-create proxy, worker mock dispatch, mock daemon controls, stuck release, approval-gated enrollment request with raw-token issue blocked, workspace/storage/tool-call/evaluation/runtime-connector/Notion external-base/agent-detail data contracts, deployment storage gate, and browser snapshot smoke",
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
            and (ROOT / "scripts" / "ui_api_parity_matrix_smoke.py").exists(),
            "Gate 4 page-by-page Vite/Next route and API parity matrix is present and machine-checkable",
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
            and file_contains("docs/AGENT_GATEWAY_CLI_SPEC.md", "Postgres routed task/execution/evidence/plan helper")
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
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_claim_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_run_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_tool_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_eval_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_artifact_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_plan_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_manifest_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_plan_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_header_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_other_agent_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_claim_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_run_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_tool_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_eval_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_artifact_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_plan_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_manifest_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_plan_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_manifest_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_non_allowlisted_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_execution_start_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_evidence_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_plan_evidence_write_v1")
            and file_contains("server.py", '("POST", "/api/agent-gateway/tool-calls")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/artifacts")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/evaluations/submit")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/agent-plans")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/plan-evidence-manifests")')
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_tool_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_eval_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_artifact_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_plan_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_manifest_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_manifest_verification_pass")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_tool_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_eval_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_artifact_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_plan_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_manifest_runtime_event_count")
            and (ROOT / "scripts" / "storage_postgres_http_write_task_smoke.py").exists(),
            "experimental Postgres HTTP task, Agent Gateway task, claim, run-start, tool/eval/artifact evidence, Agent Plan, and plan-evidence manifest write routes are explicitly allowlisted, smoke-tested, and documented",
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
                "python3 scripts/production_auth_fail_closed_smoke.py",
                "python3 scripts/security_production_readiness_smoke.py",
                "python3 scripts/agent_gateway_scope_matrix_smoke.py",
                "python3 scripts/workspace_isolation_smoke.py",
                "python3 scripts/workspace_rbac_governance_smoke.py",
                "python3 scripts/workspace_memory_session_governance_smoke.py",
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
            ],
        },
        {
            "id": "gate_4",
            "name": "UI/API Parity Before Next.js",
            "status": "started",
            "verify": [
                "python3 scripts/nextjs_parity_smoke.py",
                "cd ui/start-building-app && npm run build",
                "cd ui/next-app && npm run build",
                "python3 scripts/ui_api_parity_matrix_smoke.py",
                "python3 scripts/ui_task_run_route_parity_smoke.py",
                "python3 scripts/ui_route_naming_decision_smoke.py",
                "python3 scripts/ui_legacy_route_alias_smoke.py",
                "python3 scripts/ui_navigation_inventory_smoke.py",
                "python3 scripts/ui_route_retirement_packet_smoke.py",
                "python3 scripts/nextjs_agent_gateway_task_proxy_smoke.py",
                "python3 scripts/nextjs_worker_dispatch_once_smoke.py",
                "python3 scripts/nextjs_worker_stuck_release_smoke.py",
                "python3 scripts/nextjs_worker_daemon_control_smoke.py",
                "python3 scripts/nextjs_enrollment_request_smoke.py",
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
