#!/usr/bin/env python3
"""Verify Runtime Connector trust UI explains operator impact and readback."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CONNECTORS = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "RuntimeConnectors.tsx"
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"
SERVER = ROOT / "server.py"
TRUST_SMOKE = ROOT / "scripts" / "runtime_connector_trust_smoke.py"


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
    trust_smoke = TRUST_SMOKE.read_text(encoding="utf-8")

    trust_impact_block = extract_block(
        ui,
        'data-testid="runtime-connector-trust-impact"',
        '<div className="rounded-lg p-3 mt-3"',
    )
    copy_block = extract_block(ui, "trustedImpact", "const capabilitySummary")
    live_api_block = extract_block(
        live_api,
        "export async function loadRuntimeConnectors",
        "export async function loadAudit",
    )
    get_route = extract_block(server, 'if path == "/api/runtime-connectors":', 'if path == "/api/runtime-events":')
    trust_route = extract_block(server, 'path.startswith("/api/runtime-connectors/")', 'if path == "/api/mock-runs/start":')

    require("runtime-connector-trust-impact" in ui, "Runtime Connectors page missing trust impact test id", failures)
    require("trustImpact(connector.trust_status)" in trust_impact_block, "trust impact block does not render status-specific impact copy", failures)
    require("liveWorkerGate" in trust_impact_block, "trust impact block missing live worker gate label", failures)
    require("operatorReadback" in trust_impact_block, "trust impact block missing operator readback label", failures)
    require("auditRefs" in trust_impact_block, "trust impact block missing audit refs label", failures)
    require("connectorAuditLogs.filter" in trust_impact_block, "trust impact block does not count connector audit refs", failures)
    require("Confirmed live customer-worker execution is blocked before adapter invocation" in copy_block, "English blocked impact copy missing", failures)
    require("确认后的客户 worker 真实执行会在调用 adapter 前被阻断" in copy_block, "Chinese blocked impact copy missing", failures)
    require("review_required" in ui and "blockedImpact" in ui, "review/blocked trust states not represented in UI impact", failures)
    require('"/runtime-connectors"' in live_api_block, "live API does not load runtime connectors", failures)
    require("/trust" in live_api_block and "updateRuntimeConnectorTrust" in live_api_block, "live API does not expose trust update wiring", failures)
    require("runtime_connector_public_row" in get_route, "runtime connector list route does not return public rows", failures)
    require("update_runtime_connector_trust" in trust_route, "runtime connector trust update route missing", failures)
    require("runtime_connector_trust_blocked" in trust_smoke, "server-backed trust smoke must prove blocked live worker behavior", failures)
    require("no live adapter execution occurs" in trust_smoke, "trust smoke must describe no-live-execution expectation", failures)

    print(json.dumps({
        "operation": "runtime_connector_trust_ui_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "files": [
            str(RUNTIME_CONNECTORS.relative_to(ROOT)),
            str(LIVE_API.relative_to(ROOT)),
            str(SERVER.relative_to(ROOT)),
            str(TRUST_SMOKE.relative_to(ROOT)),
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
