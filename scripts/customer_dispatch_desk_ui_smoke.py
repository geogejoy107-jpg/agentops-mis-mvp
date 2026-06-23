#!/usr/bin/env python3
"""Verify the customer Dispatch Desk is a first-class live MIS entry point."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ui" / "start-building-app" / "src" / "app" / "App.tsx"
SIDEBAR = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "layout" / "Sidebar.tsx"
HOME = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "WorkspaceHome.tsx"
DESK = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "CustomerDispatchDesk.tsx"
PANEL = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pixel" / "CustomerDispatchPanel.tsx"
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]

EXPECTED = {
    "route_import": (APP, 'import { CustomerDispatchDesk } from "./components/pages/CustomerDispatchDesk";'),
    "route_path": (APP, 'path="/workspace/dispatch" element={<CustomerDispatchDesk />}'),
    "sidebar_label_en": (SIDEBAR, 'dispatchDesk: "Dispatch Desk"'),
    "sidebar_label_zh": (SIDEBAR, 'dispatchDesk: "派活台"'),
    "sidebar_path": (SIDEBAR, 'path: "/workspace/dispatch"'),
    "home_primary_link": (HOME, 'to="/workspace/dispatch"'),
    "home_card_link": (HOME, 'to: "/workspace/dispatch"'),
    "desk_title_en": (DESK, 'title: "Dispatch Desk"'),
    "desk_title_zh": (DESK, 'title: "派活台"'),
    "desk_live_agents": (DESK, "loadAgents(metrics)"),
    "desk_live_dashboard": (DESK, "loadDashboard()"),
    "desk_panel": (DESK, "<CustomerDispatchPanel"),
    "desk_pixel_link": (DESK, 'to="/workspace/pixel-office"'),
    "desk_worker_link": (DESK, 'to="/workspace/workers"'),
    "desk_mode_strip": (DESK, 'data-testid="dispatch-mode-strip"'),
    "desk_mode_dry_run": (DESK, "Dry-run"),
    "desk_mode_mock_ledger": (DESK, "Mock ledger write"),
    "desk_mode_approval_wall": (DESK, "Approval wall"),
    "panel_template_loader": (PANEL, "loadCustomerTaskTemplates"),
    "panel_template_run": (PANEL, "runCustomerTaskTemplateWorkflow"),
    "panel_worker_run": (PANEL, "runCustomerWorkerTaskWorkflow"),
    "panel_async_worker": (PANEL, "submitCustomerWorkerTaskJob"),
    "panel_async_template": (PANEL, "submitCustomerTaskTemplateJob"),
    "panel_execution_mode": (PANEL, "loadOperatorExecutionMode"),
    "panel_confirm_gate": (PANEL, 'const liveAdapterConfirmMissing = workerAdapter !== "mock" && !liveRuntimeConfirmed;'),
    "api_template_list": (LIVE_API, '"/workflows/customer-task-templates"'),
    "api_template_run": (LIVE_API, '"/workflows/customer-task-templates/run"'),
    "api_template_submit": (LIVE_API, '"/workflows/customer-task-templates/submit"'),
    "api_worker_task": (LIVE_API, '"/workflows/customer-worker-task"'),
    "api_worker_submit": (LIVE_API, '"/workflows/customer-worker-task/submit"'),
}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    for name, (path, marker) in EXPECTED.items():
        require(path.exists(), f"{name}: missing file {path.relative_to(ROOT)}", failures)
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        require(marker in text, f"{name}: missing marker {marker}", failures)

    desk_text = DESK.read_text(encoding="utf-8") if DESK.exists() else ""
    panel_text = PANEL.read_text(encoding="utf-8") if PANEL.exists() else ""
    require("mockData" not in desk_text, "Dispatch Desk must not import mockData", failures)
    require("Hermes/OpenClaw" in desk_text, "Dispatch Desk must state Hermes/OpenClaw confirmation boundary", failures)
    require("Mock worker 会真实写账本" in desk_text, "Dispatch Desk should explain real ledger write in Chinese", failures)
    require("confirm_run" in desk_text and "prepared-action" in desk_text, "Dispatch Desk must expose confirm/prepared-action language", failures)
    require("Customer delivery board" in panel_text and "客户交付看板" in panel_text, "Customer delivery board must remain visible", failures)
    require(not any(pattern.search(desk_text) for pattern in SECRET_PATTERNS), "Dispatch Desk contains token-like material", failures)

    output = {
        "operation": "customer_dispatch_desk_ui_smoke",
        "ok": not failures,
        "route": "/workspace/dispatch",
        "checks": len(EXPECTED) + 6,
        "failures": failures,
        "safety": {
            "static_only": True,
            "live_execution_performed": False,
            "token_omitted": True,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
