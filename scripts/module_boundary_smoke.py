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


SERVER = ROOT / "server.py"
CAPABILITIES = ROOT / "agentops_mis_runtime" / "capabilities.py"
CONNECTORS = ROOT / "agentops_mis_runtime" / "connectors.py"
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
    capabilities_text = CAPABILITIES.read_text(encoding="utf-8")
    connectors_text = CONNECTORS.read_text(encoding="utf-8") if CONNECTORS.exists() else ""
    backlog_text = BACKLOG.read_text(encoding="utf-8")
    plan_text = PLAN.read_text(encoding="utf-8") if PLAN.exists() else ""
    ci_text = CI.read_text(encoding="utf-8")
    release_text = RELEASE.read_text(encoding="utf-8")

    require(CAPABILITIES.exists(), "runtime capability module missing", failures)
    require(CONNECTORS.exists(), "runtime connector registry module missing", failures)
    require("from agentops_mis_runtime.capabilities import" in server_text, "server.py must import runtime capability module", failures)
    require("from agentops_mis_runtime.connectors import" in server_text, "server.py must import runtime connector registry module", failures)
    server_functions = function_names(SERVER)
    for helper in sorted(EXTRACTED_HELPERS):
        require(helper not in server_functions, f"server.py still defines {helper}", failures)
    for helper in sorted(EXTRACTED_CONNECTOR_HELPERS):
        require(helper not in server_functions, f"server.py still defines {helper}", failures)
    for helper, sources in imported_symbol_sources(SERVER, SERVER_CAPABILITY_IMPORTS).items():
        require(sources == {"agentops_mis_runtime.capabilities"}, f"{helper} imported from wrong or multiple modules: {sorted(sources)}", failures)
    for helper, sources in imported_symbol_sources(SERVER, EXTRACTED_CONNECTOR_HELPERS).items():
        require(sources == {"agentops_mis_runtime.connectors"}, f"{helper} imported from wrong or multiple modules: {sorted(sources)}", failures)

    imports = imported_modules(CAPABILITIES)
    connector_imports = imported_modules(CONNECTORS) if CONNECTORS.exists() else set()
    forbidden = sorted(module for module in imports if module in FORBIDDEN_RUNTIME_MODULE_IMPORTS)
    require(not forbidden, f"runtime capability module imports forbidden app/runtime dependencies: {forbidden}", failures)
    require("server" not in imports, "runtime capability module must not import server module", failures)
    connector_forbidden = sorted(module for module in connector_imports if module in {"subprocess", "http.server", "urllib.request"})
    require(not connector_forbidden, f"runtime connector module imports forbidden execution/server dependencies: {connector_forbidden}", failures)
    require("server" not in connector_imports, "runtime connector module must not import server module", failures)

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
                created_at TEXT,
                updated_at TEXT
            )"""
        )
        upsert_runtime_connector(conn, connector_rows[0])
        count = conn.execute("SELECT COUNT(*) FROM runtime_connectors").fetchone()[0]
        require(count == 1, "runtime connector upsert did not insert row", failures)
    finally:
        conn.close()

    command = "python3 scripts/module_boundary_smoke.py"
    require(command in ci_text, "module boundary smoke missing from CI", failures)
    require(command in release_text, "module boundary smoke missing from release evidence", failures)
    require("P1-05" in backlog_text and "module_boundary_smoke.py" in backlog_text, "backlog missing P1-05 module boundary evidence", failures)
    require("agentops_mis_runtime/capabilities.py" in plan_text, "module boundary plan missing runtime capability module", failures)
    require("agentops_mis_runtime/connectors.py" in plan_text, "module boundary plan missing runtime connector module", failures)

    output = {
        "ok": not failures,
        "operation": "module_boundary_smoke",
        "boundary": "agentops_mis_runtime.capabilities+connectors",
        "server_line_count": len(server_text.splitlines()),
        "module_imports": {
            "capabilities": sorted(imports),
            "connectors": sorted(connector_imports),
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
