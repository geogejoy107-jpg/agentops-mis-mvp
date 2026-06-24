#!/usr/bin/env python3
"""Verify Admin Connectors renders the commercial config status readback."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CONNECTORS = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "RuntimeConnectors.tsx"
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"
SERVER = ROOT / "server.py"
STATUS_SMOKE = ROOT / "scripts" / "commercial_config_status_smoke.py"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_(API|ADMIN)_KEY=", re.IGNORECASE),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def extract_block(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start)
    if end < 0:
        return text[start:]
    return text[start:end]


def main() -> int:
    failures: list[str] = []
    ui = RUNTIME_CONNECTORS.read_text(encoding="utf-8")
    live_api = LIVE_API.read_text(encoding="utf-8")
    server = SERVER.read_text(encoding="utf-8")
    status_smoke = STATUS_SMOKE.read_text(encoding="utf-8")

    panel = extract_block(ui, 'data-testid="commercial-config-status-panel"', "{/* Connector cards grid */}")
    loader = extract_block(live_api, "export async function loadCommercialConfigStatus", "export async function updateRuntimeConnectorTrust")
    route = extract_block(server, 'if path == "/api/commercial/config-status":', 'if path == "/api/integrations/openclaw/status":')

    expected_ui_markers = {
        "panel_test_id": 'data-testid="commercial-config-status-panel"',
        "loader_import": "loadCommercialConfigStatus",
        "parallel_load": "commercialConfigStatus",
        "english_title": 'commercialConfig: "Commercial config"',
        "chinese_title": 'commercialConfig: "商业配置"',
        "read_only_summary_en": "This panel never calls billing, cleanup, live runtimes, or exposes raw config.",
        "read_only_summary_zh": "不会调用 billing、cleanup、真实运行时，也不会暴露原始配置",
        "billing_gate_badge": "billing_call_performed",
        "cleanup_gate_badge": "cleanup_execution_performed",
        "raw_config_omitted_badge": "raw_config_omitted",
        "token_omitted_badge": "token_omitted",
        "enabled_capabilities": "enabled_capabilities.map",
        "disabled_capabilities": "disabled_capabilities.map",
        "config_sources": "commercialConfigStatus.sources.entitlements",
    }
    for label, marker in expected_ui_markers.items():
        require(marker in ui, f"missing UI marker {label}: {marker}", failures)

    require(bool(panel), "commercial config status panel block missing", failures)
    require("StatusBadge status={commercialConfigStatus.safety.read_only ? \"pass\" : \"blocked\"}" in panel, "panel must show read-only gate", failures)
    require("StatusBadge status={commercialConfigStatus.safety.billing_call_performed ? \"blocked\" : \"pass\"}" in panel, "panel must show billing no-call gate", failures)
    require("StatusBadge status={commercialConfigStatus.safety.cleanup_execution_performed ? \"blocked\" : \"pass\"}" in panel, "panel must show cleanup no-execution gate", failures)
    require("commercialConfigStatus.entitlements.edition" in panel, "panel must render entitlement edition", failures)
    require("commercialConfigStatus.retention.cleanup_approval_required" in panel, "panel must render cleanup approval gate", failures)
    require("commercialConfigStatus.retention.legal_hold_required_before_cleanup" in panel, "panel must render legal hold gate", failures)

    require("export interface CommercialConfigStatusPayload" in live_api, "liveApi missing CommercialConfigStatusPayload type", failures)
    require('optionalApiJson<Record<string, unknown>>("/commercial/config-status"' in loader, "loader must use optional read-only endpoint fallback", failures)
    require("raw_config_omitted" in loader and "token_omitted" in loader, "loader must normalize omission safety fields", failures)
    require('if path == "/api/commercial/config-status":' in route and "commercial_config_status()" in route, "server route missing", failures)
    require("agentops commercial config-status" in status_smoke, "server-backed status smoke must cover CLI command", failures)

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(f"{ui}\n{live_api}")]
    require(not secret_hits, f"secret-like marker found in UI/API source: {secret_hits}", failures)

    print(json.dumps({
        "operation": "commercial_config_status_ui_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "files": [
            str(RUNTIME_CONNECTORS.relative_to(ROOT)),
            str(LIVE_API.relative_to(ROOT)),
            str(SERVER.relative_to(ROOT)),
            str(STATUS_SMOKE.relative_to(ROOT)),
        ],
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
