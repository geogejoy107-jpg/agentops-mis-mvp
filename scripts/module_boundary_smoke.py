#!/usr/bin/env python3
"""Verify the first P1-05 strangler module boundary stays in place."""
from __future__ import annotations

import ast
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentops_mis_core.read_model_cache import ReadModelCache
from agentops_mis_core.commander_work_packages import (
    build_commander_work_packages_readback,
    commander_work_package_next_action,
    commander_work_package_status,
)
from agentops_mis_core.worker_fleet import (
    build_worker_fleet_view,
    build_worker_status_payload,
    worker_fleet_health,
)
from agentops_mis_runtime.capabilities import (
    SCHEMA_VERSION,
    runtime_connector_capability_manifest,
    runtime_connector_for_adapter,
    runtime_connector_public_row,
)
from agentops_mis_runtime.connectors import (
    runtime_connector_refresh_rows,
    runtime_connector_rows,
    upsert_runtime_connector,
)
from agentops_mis_runtime.trust import (
    apply_runtime_connector_trust_update,
    normalize_trust_status,
    runtime_connector_trust,
)


SERVER = ROOT / "server.py"
CAPABILITIES = ROOT / "agentops_mis_runtime" / "capabilities.py"
CONNECTORS = ROOT / "agentops_mis_runtime" / "connectors.py"
TRUST = ROOT / "agentops_mis_runtime" / "trust.py"
READ_MODEL_CACHE = ROOT / "agentops_mis_core" / "read_model_cache.py"
COMMANDER_WORK_PACKAGES = ROOT / "agentops_mis_core" / "commander_work_packages.py"
WORKER_FLEET = ROOT / "agentops_mis_core" / "worker_fleet.py"
BACKLOG = ROOT / "docs" / "project" / "BACKLOG.md"
PLAN = ROOT / "docs" / "MODULE_BOUNDARY_PLAN.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE = ROOT / "scripts" / "release_evidence_packet_smoke.py"

FORBIDDEN_RUNTIME_MODULE_IMPORTS = {
    "sqlite3",
    "subprocess",
    "http.server",
    "urllib.request",
}
REQUIRED_MANIFEST_KEYS = {
    "schema_version",
    "connector_id",
    "provider",
    "connector_type",
    "adapter",
    "observation_level",
    "risk_floor",
    "commercial_readiness",
    "capabilities",
    "boundaries",
    "governance",
    "manifest_hash",
}
EXTRACTED_HELPERS = {
    "runtime_connector_capability_manifest",
    "runtime_connector_for_adapter",
    "runtime_connector_public_row",
}
EXTRACTED_CONNECTOR_HELPERS = {
    "hermes_runtime_config",
    "agnesfallback_config",
    "agnesfallback_cli_command",
    "runtime_connector_refresh_rows",
    "runtime_connector_rows",
    "upsert_runtime_connector",
}
SERVER_CAPABILITY_IMPORTS = {
    "runtime_connector_for_adapter",
    "runtime_connector_public_row",
}
EXTRACTED_TRUST_HELPERS = {
    "runtime_connector_trust",
}
SERVER_TRUST_IMPORTS = {
    "apply_runtime_connector_trust_update",
    "runtime_connector_trust",
}
READ_MODEL_CACHE_FORBIDDEN_SERVER_MARKERS = {
    "READ_MODEL_CACHE_LOCK",
    "entry = READ_MODEL_CACHE.get",
    "READ_MODEL_CACHE[key]",
    '"status": "hit"',
}
EXTRACTED_WORKER_FLEET_HELPERS = {
    "build_worker_fleet_view",
    "build_worker_status_payload",
    "worker_fleet_health",
}
SERVER_WORKER_FLEET_IMPORTS = {
    "build_worker_fleet_view",
    "build_worker_status_payload",
}
EXTRACTED_COMMANDER_WORK_PACKAGE_HELPERS = {
    "build_commander_work_packages_readback",
    "commander_work_package_next_action",
    "commander_work_package_status",
}
SERVER_COMMANDER_WORK_PACKAGE_IMPORTS = {
    "build_commander_work_packages_readback",
    "commander_work_package_next_action",
    "commander_work_package_status",
}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}


def imported_symbol_sources(path: Path, symbols: set[str]) -> dict[str, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    sources = {symbol: set() for symbol in symbols}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name in sources:
                    sources[alias.name].add(node.module)
    return sources


def main() -> int:
    failures: list[str] = []
    server_text = SERVER.read_text(encoding="utf-8")
    read_model_cache_text = READ_MODEL_CACHE.read_text(encoding="utf-8") if READ_MODEL_CACHE.exists() else ""
    backlog_text = BACKLOG.read_text(encoding="utf-8")
    plan_text = PLAN.read_text(encoding="utf-8") if PLAN.exists() else ""
    ci_text = CI.read_text(encoding="utf-8")
    release_text = RELEASE.read_text(encoding="utf-8")

    require(CAPABILITIES.exists(), "runtime capability module missing", failures)
    require(CONNECTORS.exists(), "runtime connector registry module missing", failures)
    require(TRUST.exists(), "runtime connector trust module missing", failures)
    require(READ_MODEL_CACHE.exists(), "read model cache core module missing", failures)
    require(COMMANDER_WORK_PACKAGES.exists(), "commander work packages core module missing", failures)
    require(WORKER_FLEET.exists(), "worker fleet core module missing", failures)
    require("from agentops_mis_core.read_model_cache import ReadModelCache" in server_text, "server.py must import read model cache core module", failures)
    require("from agentops_mis_core.commander_work_packages import" in server_text, "server.py must import commander work packages core module", failures)
    require("from agentops_mis_core.worker_fleet import" in server_text, "server.py must import worker fleet core module", failures)
    require("from agentops_mis_runtime.capabilities import" in server_text, "server.py must import runtime capability module", failures)
    require("from agentops_mis_runtime.connectors import" in server_text, "server.py must import runtime connector registry module", failures)
    require("from agentops_mis_runtime.trust import" in server_text, "server.py must import runtime connector trust module", failures)
    server_functions = function_names(SERVER)
    commander_work_package_functions = function_names(COMMANDER_WORK_PACKAGES) if COMMANDER_WORK_PACKAGES.exists() else set()
    worker_fleet_functions = function_names(WORKER_FLEET) if WORKER_FLEET.exists() else set()
    for helper in sorted(EXTRACTED_HELPERS):
        require(helper not in server_functions, f"server.py still defines {helper}", failures)
    for helper in sorted(EXTRACTED_CONNECTOR_HELPERS):
        require(helper not in server_functions, f"server.py still defines {helper}", failures)
    for helper in sorted(EXTRACTED_TRUST_HELPERS):
        require(helper not in server_functions, f"server.py still defines {helper}", failures)
    for helper in sorted(EXTRACTED_WORKER_FLEET_HELPERS):
        require(helper not in server_functions, f"server.py still defines {helper}", failures)
        require(helper in worker_fleet_functions, f"worker fleet module missing {helper}", failures)
    for helper in sorted(EXTRACTED_COMMANDER_WORK_PACKAGE_HELPERS):
        require(helper not in server_functions, f"server.py still defines {helper}", failures)
        require(helper in commander_work_package_functions, f"commander work packages module missing {helper}", failures)
    require("worker_adapter_readiness" in server_functions, "worker_adapter_readiness must remain server-owned for runtime probing", failures)
    require("worker_adapter_readiness" not in worker_fleet_functions, "worker fleet module must not own runtime adapter probing", failures)
    for helper, sources in imported_symbol_sources(SERVER, SERVER_CAPABILITY_IMPORTS).items():
        require(sources == {"agentops_mis_runtime.capabilities"}, f"{helper} imported from wrong or multiple modules: {sorted(sources)}", failures)
    for helper, sources in imported_symbol_sources(SERVER, EXTRACTED_CONNECTOR_HELPERS).items():
        require(sources == {"agentops_mis_runtime.connectors"}, f"{helper} imported from wrong or multiple modules: {sorted(sources)}", failures)
    for helper, sources in imported_symbol_sources(SERVER, SERVER_TRUST_IMPORTS).items():
        require(sources == {"agentops_mis_runtime.trust"}, f"{helper} imported from wrong or multiple modules: {sorted(sources)}", failures)
    for helper, sources in imported_symbol_sources(SERVER, SERVER_WORKER_FLEET_IMPORTS).items():
        require(sources == {"agentops_mis_core.worker_fleet"}, f"{helper} imported from wrong or multiple modules: {sorted(sources)}", failures)
    for helper, sources in imported_symbol_sources(SERVER, SERVER_COMMANDER_WORK_PACKAGE_IMPORTS).items():
        require(sources == {"agentops_mis_core.commander_work_packages"}, f"{helper} imported from wrong or multiple modules: {sorted(sources)}", failures)

    imports = imported_modules(CAPABILITIES)
    connector_imports = imported_modules(CONNECTORS) if CONNECTORS.exists() else set()
    trust_imports = imported_modules(TRUST) if TRUST.exists() else set()
    read_model_cache_imports = imported_modules(READ_MODEL_CACHE) if READ_MODEL_CACHE.exists() else set()
    commander_work_package_imports = imported_modules(COMMANDER_WORK_PACKAGES) if COMMANDER_WORK_PACKAGES.exists() else set()
    worker_fleet_imports = imported_modules(WORKER_FLEET) if WORKER_FLEET.exists() else set()
    forbidden = sorted(module for module in imports if module in FORBIDDEN_RUNTIME_MODULE_IMPORTS)
    require(not forbidden, f"runtime capability module imports forbidden app/runtime dependencies: {forbidden}", failures)
    require("server" not in imports, "runtime capability module must not import server module", failures)
    connector_forbidden = sorted(module for module in connector_imports if module in {"subprocess", "http.server", "urllib.request"})
    require(not connector_forbidden, f"runtime connector module imports forbidden execution/server dependencies: {connector_forbidden}", failures)
    require("server" not in connector_imports, "runtime connector module must not import server module", failures)
    trust_forbidden = sorted(module for module in trust_imports if module in {"subprocess", "http.server", "urllib.request"})
    require(not trust_forbidden, f"runtime trust module imports forbidden execution/server dependencies: {trust_forbidden}", failures)
    require("server" not in trust_imports, "runtime trust module must not import server module", failures)
    cache_forbidden = sorted(module for module in read_model_cache_imports if module in {"sqlite3", "subprocess", "http.server", "urllib.request"})
    require(not cache_forbidden, f"read model cache module imports forbidden app/runtime dependencies: {cache_forbidden}", failures)
    require("server" not in read_model_cache_imports, "read model cache module must not import server module", failures)
    commander_work_package_forbidden = sorted(module for module in commander_work_package_imports if module in {"sqlite3", "subprocess", "http.server", "urllib.request"})
    require(not commander_work_package_forbidden, f"commander work packages module imports forbidden app/runtime dependencies: {commander_work_package_forbidden}", failures)
    require("server" not in commander_work_package_imports, "commander work packages module must not import server module", failures)
    worker_fleet_forbidden = sorted(module for module in worker_fleet_imports if module in {"sqlite3", "subprocess", "http.server", "urllib.request"})
    require(not worker_fleet_forbidden, f"worker fleet module imports forbidden app/runtime dependencies: {worker_fleet_forbidden}", failures)
    require("server" not in worker_fleet_imports, "worker fleet module must not import server module", failures)
    require('"rtc_hermes_default_gateway"' not in server_text[server_text.find("def refresh_runtime_connectors"):server_text.find("def run_hermes_probe")], "server.py refresh_runtime_connectors still owns connector-specific refresh policy", failures)
    for marker in sorted(READ_MODEL_CACHE_FORBIDDEN_SERVER_MARKERS):
        require(marker not in server_text, f"server.py still contains read-model cache implementation marker: {marker}", failures)
    require('"status": "hit"' in read_model_cache_text, "read model cache module missing hit metadata", failures)

    manifest = runtime_connector_capability_manifest(
        "rtc_openclaw_local",
        "openclaw",
        "local_cli",
        repo_root=ROOT,
    )
    require(REQUIRED_MANIFEST_KEYS.issubset(manifest), f"manifest missing keys: {sorted(REQUIRED_MANIFEST_KEYS - set(manifest))}", failures)
    require(manifest.get("schema_version") == SCHEMA_VERSION, "manifest schema mismatch", failures)
    require(manifest.get("boundaries", {}).get("workdir") == str(ROOT), "repo_root boundary was not injected", failures)
    require(runtime_connector_for_adapter("openclaw") == "rtc_openclaw_local", "adapter mapping failed", failures)
    public = runtime_connector_public_row({
        "runtime_connector_id": "rtc_openclaw_local",
        "capability_manifest_json": json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        "capability_policy_hash": manifest["manifest_hash"],
    })
    require(public.get("capability_manifest", {}).get("manifest_hash") == manifest["manifest_hash"], "public row did not parse manifest", failures)
    require(public.get("token_omitted") is True and public.get("raw_prompt_omitted") is True, "public row omission proof missing", failures)
    connector_rows = runtime_connector_rows()
    connector_ids = {row.get("runtime_connector_id") for row in connector_rows}
    require({"rtc_agent_gateway_local", "rtc_openclaw_local", "rtc_hermes_default_gateway", "rtc_agnesfallback_cli", "rtc_agnesfallback_openai_api"}.issubset(connector_ids), f"runtime connector rows missing expected IDs: {sorted(connector_ids)}", failures)
    require(all(row.get("capability_manifest_json") and row.get("capability_policy_hash") for row in connector_rows), "runtime connector rows missing manifest/hash", failures)
    refreshed_rows = runtime_connector_refresh_rows({
        "default_gateway": {
            "api_server_listening": False,
            "last_error": "Hermes API gateway is not listening.",
        },
        "agnesfallback": {
            "binary_exists": True,
            "api_server_listening": False,
        },
    }, now="2026-06-22T00:00:00+00:00")
    refreshed_by_id = {row.get("runtime_connector_id"): row for row in refreshed_rows}
    require(refreshed_by_id["rtc_hermes_default_gateway"]["status"] == "unavailable", "Hermes refresh status projection failed", failures)
    require(refreshed_by_id["rtc_agnesfallback_cli"]["status"] == "available", "Agnesfallback CLI refresh status projection failed", failures)
    require(refreshed_by_id["rtc_agnesfallback_openai_api"]["status"] == "unavailable", "Agnesfallback API refresh status projection failed", failures)
    require(refreshed_by_id["rtc_hermes_default_gateway"]["last_health_at"] == "2026-06-22T00:00:00+00:00", "runtime connector refresh health timestamp failed", failures)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """CREATE TABLE runtime_connectors(
                runtime_connector_id TEXT PRIMARY KEY,
                provider TEXT,
                connector_type TEXT,
                profile_name TEXT,
                base_url TEXT,
                binary_path TEXT,
                status TEXT,
                allow_real_run INTEGER,
                require_confirm_run INTEGER,
                observation_level TEXT,
                capability_manifest_json TEXT,
                capability_policy_hash TEXT,
                last_health_at TEXT,
                last_error TEXT,
                trust_status TEXT DEFAULT 'trusted',
                trust_note TEXT,
                trust_updated_at TEXT,
                created_at TEXT,
                updated_at TEXT
            )"""
        )
        upsert_runtime_connector(conn, connector_rows[0])
        count = conn.execute("SELECT COUNT(*) FROM runtime_connectors").fetchone()[0]
        require(count == 1, "runtime connector upsert did not insert row", failures)
        require(normalize_trust_status("nonsense") == "review_required", "trust status fallback failed", failures)
        trust_row = runtime_connector_trust(conn, connector_rows[0]["runtime_connector_id"], refresh=False)
        require(trust_row and trust_row.get("trust_status") == "trusted", "runtime connector trust read failed", failures)
        update = apply_runtime_connector_trust_update(
            conn,
            connector_rows[0]["runtime_connector_id"],
            {"trust_status": "blocked", "trust_note": "Smoke blocks this connector."},
            now="2026-06-22T00:00:00+00:00",
            redact_text=lambda value, limit: str(value or "")[:limit],
        )
        require(update and update.get("after", {}).get("trust_status") == "blocked", "runtime connector trust update failed", failures)
    finally:
        conn.close()
    cache = ReadModelCache(ttl_sec=10, max_items=2)
    headers = {"X-AgentOps-Workspace-Id": "ws_smoke"}
    auth_ctx = {"mode": "agent_token", "workspace_id": "ws_smoke", "agent_id": "agt_smoke", "scopes": ["tasks:read"], "token_id": "fixture_token_ref"}
    first = cache.cached("smoke", {"limit": ["1"]}, headers, lambda: {"value": "one"}, auth_ctx)
    second = cache.cached("smoke", {"limit": ["1"]}, headers, lambda: {"value": "two"}, auth_ctx)
    bypass = cache.cached("smoke", {"limit": ["1"], "refresh_cache": ["true"]}, headers, lambda: {"value": "fresh"}, auth_ctx)
    require(first.get("read_model_cache", {}).get("status") == "miss", "read model cache first read should miss", failures)
    require(second.get("read_model_cache", {}).get("status") == "hit" and second.get("value") == "one", "read model cache second read should hit original payload", failures)
    require(bypass.get("read_model_cache", {}).get("status") == "bypass" and bypass.get("value") == "fresh", "read model cache refresh should bypass", failures)
    require("fixture_token_ref" not in json.dumps([first, second, bypass], ensure_ascii=False), "read model cache leaked token-like auth ref", failures)
    daemons = [{
        "adapter": "mock",
        "agent_id": "agt_worker_local_smoke",
        "running": True,
        "worker_status": "running",
        "pid": 4242,
        "processed": 3,
        "iterations": 4,
        "consecutive_errors": 0,
        "total_errors": 0,
        "state_updated_at": "2026-06-22T00:00:00+00:00",
    }]
    remote_fleet = {
        "status": "attention",
        "remote_worker_count": 1,
        "total_remote_enrollments": 1,
        "active_enrollments": 1,
        "fresh_enrollments": 0,
        "stale_enrollments": 1,
        "never_seen_enrollments": 0,
        "active_sessions": 0,
        "remote_workers": [{
            "agent_id": "agt_worker_remote_smoke",
            "agent_name": "Remote Smoke Worker",
            "workspace_id": "local-demo",
            "runtime_type": "mock",
            "token_status": "active",
            "heartbeat_state": "stale",
            "active_session_count": 0,
            "last_heartbeat_at": "2026-06-22T00:00:00+00:00",
            "scope_count": 3,
            "token_ref": "safe_ref_remote",
        }],
    }
    worker_agents = [{
        "agent_id": "agt_worker_local_smoke",
        "name": "Local Smoke Worker",
        "runtime_type": "mock",
        "status": "running",
        "updated_at": "2026-06-22T00:00:00+00:00",
    }, {
        "agent_id": "agt_worker_registered_smoke",
        "name": "Registered Smoke Worker",
        "runtime_type": "mock",
        "status": "idle",
        "updated_at": "2026-06-22T00:00:00+00:00",
    }]
    stuck_tasks = [{"task_id": "tsk_worker_stuck_smoke"}]
    stuck_jobs = [{"job_id": "job_worker_stuck_smoke", "workflow_type": "customer_worker", "status": "running", "age_sec": 901, "stuck_reason": "threshold"}]
    adapter_readiness = {"summary": {"recommended_adapter": "mock"}}
    status_payload = build_worker_status_payload(
        worker_agents=worker_agents,
        worker_runs=[{"run_id": "run_worker_smoke", "status": "completed"}],
        worker_tasks=[{"task_id": "tsk_worker_pending_smoke", "status": "planned"}],
        worker_events=[{"event_id": "evt_worker_smoke", "event_type": "task.pull"}],
        daemons=daemons,
        stuck_tasks=stuck_tasks,
        remote_fleet=remote_fleet,
        stuck_workflow_jobs=stuck_jobs,
        adapter_readiness=adapter_readiness,
    )
    fleet_view = build_worker_fleet_view(
        daemons=daemons,
        remote_fleet=remote_fleet,
        adapter_readiness=adapter_readiness["summary"],
        stuck_tasks=stuck_tasks,
        stuck_workflow_jobs=stuck_jobs,
        worker_agents=worker_agents,
    )
    health = worker_fleet_health(status_payload)
    require(status_payload.get("status") == "attention", "worker status payload did not reflect stale remote attention", failures)
    require(status_payload.get("fleet_health", {}).get("overall") == "blocked", "worker status payload missing blocked fleet health", failures)
    require(fleet_view.get("summary", {}).get("lane_count") == 3, "worker fleet view did not build expected lanes", failures)
    require(fleet_view.get("summary", {}).get("lane_counts", {}).get("local_daemon") == 1, "worker fleet view missing local daemon lane", failures)
    require(fleet_view.get("summary", {}).get("lane_counts", {}).get("remote_worker") == 1, "worker fleet view missing remote worker lane", failures)
    require(fleet_view.get("summary", {}).get("lane_counts", {}).get("registered_worker") == 1, "worker fleet view missing registered worker lane", failures)
    require(fleet_view.get("safety", {}).get("read_only") is True, "worker fleet view must remain read-only", failures)
    require(all(lane.get("token_omitted") is True and lane.get("session_id_omitted") is True for lane in fleet_view.get("lanes", [])), "worker fleet lanes missing omission proof", failures)
    require(health.get("recommended_actions"), "worker fleet health missing recommended actions", failures)
    planned_task = {"task_id": "tsk_cmd_smoke_strategy", "status": "planned"}
    completed_task = {"task_id": "tsk_cmd_smoke_qa", "status": "completed"}
    require(commander_work_package_status(planned_task, None, {}) == "planned", "commander planned package status failed", failures)
    require(commander_work_package_status(completed_task, None, {"artifacts": 1}) == "ready_for_review", "commander ready-for-review status failed", failures)
    commander_item = {
        "task_id": "tsk_cmd_smoke_strategy",
        "project_id": "proj_cmd_smoke",
        "status": "planned",
        "package_status": "planned",
        "localization_gate": {"status": "recorded"},
        "coding_evidence_gate": {"status": "partial"},
        "recommended_action": commander_work_package_next_action({"task_id": "tsk_cmd_smoke_strategy", "package_status": "planned"}),
    }
    commander_readback = build_commander_work_packages_readback(
        packages=[commander_item],
        workspace_id="local-demo",
        project_id="proj_cmd_smoke",
        plan_id="cmdplan_smoke",
        status_filter="planned",
        limit=5,
        localization_artifact_type="commander_repo_map_localization",
        coding_evidence_artifact_types=["commander_patch_manifest", "commander_test_log"],
    )
    require(commander_readback.get("operation") == "work_packages_readback", "commander readback operation mismatch", failures)
    require(commander_readback.get("summary", {}).get("total") == 1, "commander readback summary total failed", failures)
    require((commander_readback.get("summary", {}).get("localization") or {}).get("coverage_percent") == 100.0, "commander localization coverage failed", failures)
    require((commander_readback.get("summary", {}).get("coding_evidence") or {}).get("partial") == 1, "commander coding evidence summary failed", failures)
    require(commander_readback.get("safety", {}).get("read_only") is True, "commander readback must stay read-only", failures)
    require(commander_readback.get("recommended_next_actions"), "commander readback missing next actions", failures)

    command = "python3 scripts/module_boundary_smoke.py"
    require(command in ci_text, "module boundary smoke missing from CI", failures)
    require(command in release_text, "module boundary smoke missing from release evidence", failures)
    require("P1-05" in backlog_text and "module_boundary_smoke.py" in backlog_text, "backlog missing P1-05 module boundary evidence", failures)
    require("agentops_mis_runtime/capabilities.py" in plan_text, "module boundary plan missing runtime capability module", failures)
    require("agentops_mis_runtime/connectors.py" in plan_text, "module boundary plan missing runtime connector module", failures)
    require("agentops_mis_runtime/trust.py" in plan_text, "module boundary plan missing runtime trust module", failures)
    require("agentops_mis_core/read_model_cache.py" in plan_text, "module boundary plan missing read model cache module", failures)
    require("agentops_mis_core/commander_work_packages.py" in plan_text, "module boundary plan missing commander work packages module", failures)
    require("agentops_mis_core/worker_fleet.py" in plan_text, "module boundary plan missing worker fleet module", failures)

    output = {
        "ok": not failures,
        "operation": "module_boundary_smoke",
        "boundary": "agentops_mis_runtime.capabilities+connectors+trust + agentops_mis_core.read_model_cache+commander_work_packages+worker_fleet",
        "server_line_count": len(server_text.splitlines()),
        "module_imports": {
            "capabilities": sorted(imports),
            "connectors": sorted(connector_imports),
            "trust": sorted(trust_imports),
            "read_model_cache": sorted(read_model_cache_imports),
            "commander_work_packages": sorted(commander_work_package_imports),
            "worker_fleet": sorted(worker_fleet_imports),
        },
        "live_execution_performed": False,
        "ledger_mutated": False,
        "token_omitted": True,
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
