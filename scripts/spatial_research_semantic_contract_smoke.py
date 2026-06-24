#!/usr/bin/env python3
"""Static contract smoke for the Research District semantic map layer."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "ui" / "start-building-app" / "src" / "app"
CONTRACT = APP_ROOT / "spatial" / "researchDistrictSemanticContract.ts"
PIXEL_MODEL = APP_ROOT / "components" / "pixel" / "pixelModel.ts"
APP = APP_ROOT / "App.tsx"

ALLOWED_AUTHORITY_KINDS = {
    "workspace",
    "agent",
    "task",
    "run",
    "approval",
    "memory",
    "artifact",
    "evaluation",
    "audit",
    "template",
    "route",
}
ALLOWED_INTERACTIONS = {"navigate", "inspect", "operate"}
ALLOWED_METRICS = {
    "totalAgents",
    "totalRuns",
    "activeRuns",
    "pendingApprovals",
    "failedQualityGates",
    "memoryCandidates",
    "failedRuns",
    "blockedTasks",
    "auditEvents",
    "runtimeHealth",
    "externalSyncState",
    "latestAudit",
}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def registered_routes() -> set[str]:
    app = APP.read_text(encoding="utf-8")
    return set(re.findall(r'<Route\s+path="([^"]+)"', app))


def pixel_zone_routes() -> dict[str, str]:
    model = PIXEL_MODEL.read_text(encoding="utf-8")
    zone_blocks = re.findall(r'\{\s*id:\s*"([^"]+)",.*?route:\s*"([^"]+)",.*?\n\s*\}', model, flags=re.S)
    return dict(zone_blocks)


def main() -> int:
    failures: list[str] = []
    contract = CONTRACT.read_text(encoding="utf-8")
    zone_routes = pixel_zone_routes()
    routes = registered_routes()

    require("formalRoute: zone.route" in contract, "formalRoute must derive from PIXEL_ZONES route", failures)
    require('routeAuthority: "agentops-mis"' in contract, "MIS route authority marker missing", failures)
    require('visualAuthority: "spatial-map-is-not-ledger"' in contract, "visual-not-ledger marker missing", failures)
    require("RESEARCH_DISTRICT_SEMANTIC_BY_ZONE" in contract, "zone lookup export missing", failures)

    calls = re.findall(
        r'semanticObject\(\s*\n\s*"([^"]+)",\s*\n\s*"([^"]+)",\s*\n\s*"([^"]+)",\s*\n\s*"([^"]+)",\s*\n\s*"([^"]+)",',
        contract,
    )
    contract_zones = [zone_id for zone_id, *_ in calls]
    require(len(calls) == len(zone_routes), f"expected one semantic object per Pixel zone: calls={len(calls)} zones={len(zone_routes)}", failures)
    require(set(contract_zones) == set(zone_routes), f"zone coverage mismatch: missing={sorted(set(zone_routes) - set(contract_zones))} extra={sorted(set(contract_zones) - set(zone_routes))}", failures)
    require(len(contract_zones) == len(set(contract_zones)), "semantic zone IDs must be unique", failures)

    for zone_id, authority_class, authority_kind, metric_key, interaction in calls:
        require(authority_class, f"authority class missing for {zone_id}", failures)
        require(authority_kind in ALLOWED_AUTHORITY_KINDS, f"unknown authority kind for {zone_id}: {authority_kind}", failures)
        require(metric_key in ALLOWED_METRICS, f"unknown metric key for {zone_id}: {metric_key}", failures)
        require(interaction in ALLOWED_INTERACTIONS, f"unknown interaction for {zone_id}: {interaction}", failures)
        route = zone_routes.get(zone_id)
        require(route in routes, f"Pixel zone route is not registered in App.tsx for {zone_id}: {route}", failures)

    forbidden = [
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        "raw.githubusercontent.com",
        "private-user-images.githubusercontent.com",
        "Star-Office",
        "Star Office",
    ]
    for token in forbidden:
        require(token not in contract, f"forbidden visual/third-party token in semantic contract: {token}", failures)

    output = {
        "ok": not failures,
        "operation": "spatial_research_semantic_contract_smoke",
        "semantic_objects": len(calls),
        "pixel_zones": len(zone_routes),
        "registered_routes_checked": len(routes),
        "contract": "Research District semantic objects are route-bound projections of AgentOps MIS authority; the spatial map is not a second ledger.",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "third_party_assets_copied": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
