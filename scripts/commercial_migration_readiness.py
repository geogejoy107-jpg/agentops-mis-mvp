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
            and (ROOT / "scripts" / "nextjs_parity_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_playwright_snapshot_smoke.py").exists(),
            "parallel Next.js App Router track has API proxy, workspace data contract, and browser snapshot smoke",
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
            and file_contains("server.py", "repo_list_workspace_tasks")
            and file_contains("server.py", "storage_backend_status")
            and (ROOT / "agentops_mis_storage" / "postgres.py").exists()
            and (ROOT / "agentops_mis_storage" / "parity_fixture.py").exists()
            and (ROOT / "scripts" / "storage_boundary_sqlite_smoke.py").exists()
            and (ROOT / "scripts" / "storage_postgres_boundary_parity_smoke.py").exists()
            and (ROOT / "scripts" / "storage_postgres_route_read_model_smoke.py").exists()
            and (ROOT / "scripts" / "storage_backend_selection_smoke.py").exists(),
            "workspace-scoped helpers, isolated SQLite smoke, Postgres container parity, adapter SQL contract, optional psycopg adapter, shared boundary fixture parity, route read-model parity, and fail-closed backend selection are present",
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
