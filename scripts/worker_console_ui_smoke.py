#!/usr/bin/env python3
"""Verify the dedicated Worker Console UI stays wired to live Worker APIs."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "ui" / "start-building-app" / "src" / "app" / "App.tsx"
SIDEBAR = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "layout" / "Sidebar.tsx"
HOME = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "WorkspaceHome.tsx"
CONSOLE = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "WorkerConsole.tsx"
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
    "route_import": (APP, 'import { WorkerConsole } from "./components/pages/WorkerConsole";'),
    "route_path": (APP, 'path="/workspace/workers" element={<WorkerConsole />}'),
    "sidebar_label_en": (SIDEBAR, 'workerConsole: "Worker Console"'),
    "sidebar_label_zh": (SIDEBAR, 'workerConsole: "Worker 控制台"'),
    "sidebar_path": (SIDEBAR, 'path: "/workspace/workers"'),
    "home_link": (HOME, 'to: "/workspace/workers"'),
    "console_title_en": (CONSOLE, 'title: "Worker Control Console"'),
    "console_title_zh": (CONSOLE, 'title: "Worker 控制台"'),
    "real_status_loader": (CONSOLE, "loadWorkerStatus()"),
    "real_fleet_loader": (CONSOLE, "loadWorkerFleet()"),
    "real_fleet_hygiene_loader": (CONSOLE, "loadWorkerFleetHygiene({ limit: 8 })"),
    "real_readiness_loader": (CONSOLE, "loadWorkerAdapterReadiness()"),
    "real_execution_mode_loader": (CONSOLE, "loadOperatorExecutionMode(selectedAdapter, confirmRun, 8)"),
    "real_start_check_loader": (CONSOLE, "loadOperatorStartCheck(selectedAdapter, 8)"),
    "local_install_packet_panel": (CONSOLE, 'data-testid="worker-local-install-packet"'),
    "local_install_service_install": (CONSOLE, "serviceInstall.preview_command"),
    "local_install_confirm_install": (CONSOLE, "serviceInstall.confirm_command"),
    "local_install_service_check": (CONSOLE, "serviceInstall.verify_command"),
    "local_install_no_service_load": (CONSOLE, "serviceInstall.loads_service"),
    "local_install_no_server_shell": (CONSOLE, "serviceInstall.server_executes_shell"),
    "local_install_first_safe": (CONSOLE, "firstSafeHasInstall"),
    "fleet_hygiene_apply_api": (CONSOLE, "applyWorkerFleetHygiene({"),
    "fleet_hygiene_panel": (CONSOLE, 'data-testid="worker-fleet-hygiene-panel"'),
    "fleet_hygiene_confirm_gate": (CONSOLE, "disabled={Boolean(busyAction) || !confirmCleanup || hygieneActionsAvailable === 0}"),
    "fleet_hygiene_no_live": (CONSOLE, "fleetHygiene?.live_execution_performed"),
    "fleet_hygiene_token_omitted": (CONSOLE, "fleetHygiene?.token_omitted"),
    "dispatch_api": (CONSOLE, "dispatchLocalWorkerOnce({"),
    "start_daemon_api": (CONSOLE, "startLocalWorkerDaemon({"),
    "restart_daemon_api": (CONSOLE, "restartLocalWorkerDaemon({"),
    "stop_daemon_api": (CONSOLE, 'stopLocalWorkerDaemon("all")'),
    "live_confirm_gate": (CONSOLE, 'const liveBlocked = selectedAdapter !== "mock" && !confirmRun;'),
    "live_confirm_disabled_dispatch": (CONSOLE, "disabled={Boolean(busyAction) || liveBlocked}"),
    "ledger_links_task": (CONSOLE, "to={`/admin/tasks/${lastDispatch.task_id}`}"),
    "ledger_links_run": (CONSOLE, "to={`/admin/runs/${lastDispatch.run_id}`}"),
    "safety_read_only": (CONSOLE, "executionMode?.safety.read_only"),
    "safety_no_server_shell": (CONSOLE, "executionMode?.safety.server_executes_shell"),
    "safety_token_omitted": (CONSOLE, "executionMode?.safety.token_omitted"),
    "api_worker_status": (LIVE_API, '"/workers/status"'),
    "api_worker_readiness": (LIVE_API, '"/workers/adapter-readiness"'),
    "api_worker_fleet_hygiene": (LIVE_API, '"/workers/fleet/hygiene"'),
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
    console_text = CONSOLE.read_text(encoding="utf-8") if CONSOLE.exists() else ""
    require("mock" in console_text and "hermes" in console_text and "openclaw" in console_text, "worker adapters missing", failures)
    require("Fleet hygiene" in console_text and "Fleet 清理" in console_text, "fleet hygiene labels missing", failures)
    require("confirm_cleanup" in LIVE_API.read_text(encoding="utf-8"), "hygiene apply must send confirm_cleanup", failures)
    require("mockData" not in console_text, "Worker Console must not import mockData", failures)
    require(not any(pattern.search(console_text) for pattern in SECRET_PATTERNS), "Worker Console contains token-like material", failures)
    output = {
        "operation": "worker_console_ui_smoke",
        "ok": not failures,
        "route": "/workspace/workers",
        "checks": len(EXPECTED) + 3,
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
