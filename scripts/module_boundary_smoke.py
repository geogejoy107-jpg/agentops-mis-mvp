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
from agentops_mis_runtime.capabilities import (
    SCHEMA_VERSION,
    runtime_connector_capability_manifest,
    runtime_connector_for_adapter,
    runtime_connector_public_row,
)
from agentops_mis_runtime.connectors import (
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
    require("from agentops_mis_core.read_model_cache import ReadModelCache" in server_text, "server.py must import read model cache core module", failures)
    require("from agentops_mis_runtime.capabilities import" in server_text, "server.py must import runtime capability module", failures)
    require("from agentops_mis_runtime.connectors import" in server_text, "server.py must import runtime connector registry module", failures)
    require("from agentops_mis_runtime.trust import" in server_text, "server.py must import runtime connector trust module", failures)
    server_functions = function_names(SERVER)
    for helper in sorted(EXTRACTED_HELPERS):
        require(helper not in server_functions, f"server.py still defines {helper}", failures)
    for helper in sorted(EXTRACTED_CONNECTOR_HELPERS):
        require(helper not in server_functions, f"server.py still defines {helper}", failures)
    for helper in sorted(EXTRACTED_TRUST_HELPERS):
        require(helper not in server_functions, f"server.py still defines {helper}", failures)
    for helper, sources in imported_symbol_sources(SERVER, SERVER_CAPABILITY_IMPORTS).items():
        require(sources == {"agentops_mis_runtime.capabilities"}, f"{helper} imported from wrong or multiple modules: {sorted(sources)}", failures)
    for helper, sources in imported_symbol_sources(SERVER, EXTRACTED_CONNECTOR_HELPERS).items():
        require(sources == {"agentops_mis_runtime.connectors"}, f"{helper} imported from wrong or multiple modules: {sorted(sources)}", failures)
    for helper, sources in imported_symbol_sources(SERVER, SERVER_TRUST_IMPORTS).items():
        require(sources == {"agentops_mis_runtime.trust"}, f"{helper} imported from wrong or multiple modules: {sorted(sources)}", failures)

    imports = imported_modules(CAPABILITIES)
    connector_imports = imported_modules(CONNECTORS) if CONNECTORS.exists() else set()
    trust_imports = imported_modules(TRUST) if TRUST.exists() else set()
    read_model_cache_imports = imported_modules(READ_MODEL_CACHE) if READ_MODEL_CACHE.exists() else set()
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
    auth_ctx = {"mode": "agent_token", "workspace_id": "ws_smoke", "agent_id": "agt_smoke", "scopes": ["tasks:read"], "token_id": "agtok_fake_secret"}
    first = cache.cached("smoke", {"limit": ["1"]}, headers, lambda: {"value": "one"}, auth_ctx)
    second = cache.cached("smoke", {"limit": ["1"]}, headers, lambda: {"value": "two"}, auth_ctx)
    bypass = cache.cached("smoke", {"limit": ["1"], "refresh_cache": ["true"]}, headers, lambda: {"value": "fresh"}, auth_ctx)
    require(first.get("read_model_cache", {}).get("status") == "miss", "read model cache first read should miss", failures)
    require(second.get("read_model_cache", {}).get("status") == "hit" and second.get("value") == "one", "read model cache second read should hit original payload", failures)
    require(bypass.get("read_model_cache", {}).get("status") == "bypass" and bypass.get("value") == "fresh", "read model cache refresh should bypass", failures)
    require("agtok_fake_secret" not in json.dumps([first, second, bypass], ensure_ascii=False), "read model cache leaked token-like auth ref", failures)

    command = "python3 scripts/module_boundary_smoke.py"
    require(command in ci_text, "module boundary smoke missing from CI", failures)
    require(command in release_text, "module boundary smoke missing from release evidence", failures)
    require("P1-05" in backlog_text and "module_boundary_smoke.py" in backlog_text, "backlog missing P1-05 module boundary evidence", failures)
    require("agentops_mis_runtime/capabilities.py" in plan_text, "module boundary plan missing runtime capability module", failures)
    require("agentops_mis_runtime/connectors.py" in plan_text, "module boundary plan missing runtime connector module", failures)
    require("agentops_mis_runtime/trust.py" in plan_text, "module boundary plan missing runtime trust module", failures)
    require("agentops_mis_core/read_model_cache.py" in plan_text, "module boundary plan missing read model cache module", failures)

    output = {
        "ok": not failures,
        "operation": "module_boundary_smoke",
        "boundary": "agentops_mis_runtime.capabilities+connectors+trust + agentops_mis_core.read_model_cache",
        "server_line_count": len(server_text.splitlines()),
        "module_imports": {
            "capabilities": sorted(imports),
            "connectors": sorted(connector_imports),
            "trust": sorted(trust_imports),
            "read_model_cache": sorted(read_model_cache_imports),
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
