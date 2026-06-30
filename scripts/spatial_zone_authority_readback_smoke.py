#!/usr/bin/env python3
"""Verify Pixel Office Zone Inspector reads back semantic authority metadata."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "ui" / "start-building-app" / "src" / "app"
ZONE_INSPECTOR = APP_ROOT / "components" / "pixel" / "ZoneInspector.tsx"
CONTRACT = APP_ROOT / "spatial" / "researchDistrictSemanticContract.ts"


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    inspector = ZONE_INSPECTOR.read_text(encoding="utf-8")
    contract = CONTRACT.read_text(encoding="utf-8")

    required_inspector_markers = {
        "contract_import": "RESEARCH_DISTRICT_SEMANTIC_BY_ZONE",
        "zone_lookup": "RESEARCH_DISTRICT_SEMANTIC_BY_ZONE.get(focusZone.id)",
        "test_id": 'data-testid="semantic-authority-readback"',
        "authority_class": "semanticObject.authorityClass",
        "authority_kind": "semanticObject.authorityKind",
        "formal_route": "semanticObject.formalRoute",
        "route_authority": "semanticObject.routeAuthority",
        "visual_authority": "semanticObject.visualAuthority",
        "localized_description": "semanticObject.description[locale]",
        "zh_label": "语义权威",
        "en_label": "Semantic authority",
    }
    for label, marker in required_inspector_markers.items():
        require(marker in inspector, f"missing Zone Inspector marker {label}: {marker}", failures)

    require('routeAuthority: "agentops-mis"' in contract, "semantic contract must keep AgentOps MIS as route authority", failures)
    require('visualAuthority: "spatial-map-is-not-ledger"' in contract, "semantic contract must keep map as non-ledger visual projection", failures)

    forbidden_tokens = [
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        "raw.githubusercontent.com",
        "private-user-images.githubusercontent.com",
        "Star-Office",
        "Star Office",
        "ledger_mutated: true",
        "live_execution_performed: true",
    ]
    combined = f"{inspector}\n{contract}"
    for token in forbidden_tokens:
        require(token not in combined, f"forbidden asset/runtime token found: {token}", failures)

    print(json.dumps({
        "operation": "spatial_zone_authority_readback_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "files": [
            str(ZONE_INSPECTOR.relative_to(ROOT)),
            str(CONTRACT.relative_to(ROOT)),
        ],
        "contract": "Zone Inspector displays semantic authority metadata from the Research District contract while preserving AgentOps MIS as the authority system.",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "third_party_assets_copied": False,
            "token_omitted": True,
        },
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
