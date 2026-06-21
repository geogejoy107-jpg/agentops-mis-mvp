#!/usr/bin/env python3
"""Static smoke for the Next.js commercial parity track."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEXT_APP = ROOT / "ui" / "next-app"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    package_path = NEXT_APP / "package.json"
    package = json.loads(read_text(package_path))
    dependencies = package.get("dependencies", {})
    scripts = package.get("scripts", {})

    required_files = [
        NEXT_APP / "app" / "layout.tsx",
        NEXT_APP / "app" / "workspace" / "page.tsx",
        NEXT_APP / "app" / "api" / "mis" / "[...path]" / "route.ts",
        NEXT_APP / "src" / "components" / "WorkspaceDashboard.tsx",
        NEXT_APP / "src" / "lib" / "mis.ts",
        NEXT_APP / "src" / "styles" / "globals.css",
    ]

    for path in required_files:
        require(path.exists(), f"missing Next.js parity file: {path.relative_to(ROOT)}")

    route_text = read_text(NEXT_APP / "app" / "api" / "mis" / "[...path]" / "route.ts")
    dashboard_text = read_text(NEXT_APP / "src" / "components" / "WorkspaceDashboard.tsx")
    lib_text = read_text(NEXT_APP / "src" / "lib" / "mis.ts")

    require(dependencies.get("next") == "16.2.9", "Next.js version is not pinned to the selected migration version")
    require(dependencies.get("react") == "19.2.7", "React version is not pinned to the selected migration version")
    require("build" in scripts and "next build" in scripts["build"], "Next.js build script is missing")
    require("AGENTOPS_API_BASE" in route_text, "API proxy must be configurable with AGENTOPS_API_BASE")
    require("/dashboard/metrics" in lib_text, "workspace parity data must include dashboard metrics")
    require("/tasks" in lib_text and "/runs" in lib_text and "/approvals" in lib_text, "workspace parity data misses core ledgers")
    require("loadWorkspaceSnapshot" in dashboard_text, "workspace page must consume the shared Next.js MIS data contract")

    print(json.dumps({
        "ok": True,
        "next_app": str(NEXT_APP.relative_to(ROOT)),
        "routes": ["/workspace", "/api/mis/[...path]"],
        "stack": {
            "next": dependencies.get("next"),
            "react": dependencies.get("react"),
            "typescript": package.get("devDependencies", {}).get("typescript"),
        },
        "api_provider": "AGENTOPS_API_BASE or http://127.0.0.1:8765/api",
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
