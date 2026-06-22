#!/usr/bin/env python3
"""Verify Pixel Office stays a native MIS visualizer, not an authority layer."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIXEL_OFFICE = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "PixelOffice.tsx"
CUSTOMER_DISPATCH = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pixel" / "CustomerDispatchPanel.tsx"
WORKSPACE_HOME = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "WorkspaceHome.tsx"
PIXEL_MODEL = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pixel" / "pixelModel.ts"
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"


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


def main() -> int:
    failures: list[str] = []
    pixel = PIXEL_OFFICE.read_text(encoding="utf-8")
    dispatch = CUSTOMER_DISPATCH.read_text(encoding="utf-8")
    home = WORKSPACE_HOME.read_text(encoding="utf-8")
    model = PIXEL_MODEL.read_text(encoding="utf-8")
    live_api = LIVE_API.read_text(encoding="utf-8")
    combined = "\n".join([pixel, dispatch, home, model, live_api])

    expected_markers = {
        "native_page": "export function PixelOffice()",
        "native_map_component": "<PixelOperatingMap",
        "customer_dispatch_component": "<CustomerDispatchPanel",
        "operations_bar_component": "<OperationsBar",
        "mis_state_loaders": "loadAgents(metrics)",
        "route_contract": "Every room is a route into an existing MIS page",
        "state_source_copy": "Agent placement comes from AgentOps MIS agents, tasks, runs, approvals, memories and audit events",
        "asset_boundary_copy": "No Star-Office, paid tileset or third-party sprite assets are copied into the product UI",
        "authority_copy": "AgentOps MIS remains the authority system for state, permissions, evaluations and audit.",
        "zh_authority_copy": "AgentOps MIS 仍然是状态、权限、评估和审计的权威系统。",
        "legacy_optional_url": "VITE_STAR_OFFICE_URL",
        "legacy_external_link_only": "window.open(route, \"_blank\", \"noreferrer\")",
        "workspace_home_no_assets_copy": "Original CSS preview only · no Star-Office assets copied",
        "zone_routes": "route:",
        "formal_ledger_route": "/admin/runs",
        "customer_dispatch_mis_workflow": "runCustomerWorkerTaskWorkflow",
        "customer_dispatch_async_mis_workflow": "submitCustomerWorkerTaskJob",
        "template_workflow_api": "runCustomerTaskTemplateWorkflow",
        "report_archive_api": "persistCustomerProjectReportArtifact",
        "live_api_customer_worker": '"/workflows/customer-worker-task"',
        "live_api_customer_worker_submit": '"/workflows/customer-worker-task/submit"',
        "live_adapter_confirm": "liveAdapterConfirmMissing",
        "ledger_evidence_copy": "Mock worker writes real ledger evidence; Hermes/OpenClaw require explicit confirmation.",
    }
    for label, marker in expected_markers.items():
        require(marker in combined, f"missing {label}: {marker}", failures)

    forbidden_markers = {
        "pixel_office_iframe": "<iframe",
        "star_office_api_push": "/agent-push",
        "star_office_set_state": "/set_state",
        "star_office_import": "from \"Star-Office",
        "star_office_asset_path": "Star-Office-UI/assets",
        "external_visualizer_authority": "Star Office remains the authority",
    }
    for label, marker in forbidden_markers.items():
        require(marker not in combined, f"forbidden {label}: {marker}", failures)

    asset_like_paths = re.findall(r"['\"]([^'\"]+\.(?:png|jpe?g|gif|webp|bmp|aseprite|tmx|tsx|tileset|sprite))['\"]", combined, flags=re.IGNORECASE)
    require(not asset_like_paths, f"Pixel Office source should not import bitmap/tile/sprite assets: {asset_like_paths[:5]}", failures)

    star_refs = [line.strip() for line in combined.splitlines() if "Star-Office" in line or "Star Office" in line]
    allowed_star_refs = [
        line for line in star_refs
        if any(allowed in line for allowed in [
            "VITE_STAR_OFFICE_URL",
            "Legacy Star Office",
            "Legacy Star Office View",
            "legacy Star Office",
            "旧 Star Office",
            "可打开旧 Star Office",
            "未配置旧 Star Office",
            "Star Office available",
            "Star Office not configured",
            "Star Office link is hidden",
            "Star-Office, paid tileset",
            "Star-Office、付费 tileset",
            "Star-Office assets copied",
            "不把 Star-Office",
        ])
    ]
    require(len(star_refs) == len(allowed_star_refs), f"unexpected Star-Office references: {star_refs}", failures)

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(combined)]
    require(not secret_hits, f"secret-like marker found in Pixel Office boundary source: {secret_hits}", failures)

    output = {
        "ok": not failures,
        "operation": "pixel_office_visualizer_boundary_smoke",
        "files": [
            str(PIXEL_OFFICE.relative_to(ROOT)),
            str(CUSTOMER_DISPATCH.relative_to(ROOT)),
            str(WORKSPACE_HOME.relative_to(ROOT)),
            str(PIXEL_MODEL.relative_to(ROOT)),
            str(LIVE_API.relative_to(ROOT)),
        ],
        "contract": "Pixel Office is a native React/CSS visualizer and customer dispatch entry; MIS APIs, ledgers, approvals and evidence remain authoritative.",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
