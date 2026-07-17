#!/usr/bin/env python3
"""HTTP smoke for Next.js legacy task/run route aliases."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "ui_legacy_route_alias_v1"

sys.path.insert(0, str(SCRIPTS))

from nextjs_playwright_snapshot_smoke import free_port, require, restore_next_env, run, start_process, stop_process, wait_http  # noqa: E402


ALIASES = [
    {
        "id": "task_detail",
        "legacy_path": "/admin/tasks/tsk_alias_probe",
        "target_path": "/workspace/tasks/tsk_alias_probe",
        "source_file": "ui/next-app/app/admin/tasks/[taskId]/page.tsx",
    },
    {
        "id": "run_ledger",
        "legacy_path": "/admin/runs",
        "target_path": "/workspace/runs",
        "source_file": "ui/next-app/app/admin/runs/page.tsx",
    },
    {
        "id": "run_detail",
        "legacy_path": "/admin/runs/run_alias_probe",
        "target_path": "/workspace/runs/run_alias_probe",
        "source_file": "ui/next-app/app/admin/runs/[runId]/page.tsx",
    },
]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        return None


def assert_static_aliases() -> None:
    for alias in ALIASES:
        source = ROOT / alias["source_file"]
        require(source.exists(), f"missing legacy alias route file: {alias['source_file']}")
        text = source.read_text(encoding="utf-8")
        require("next/navigation" in text and "redirect(" in text, f"{alias['id']} alias must use Next redirect()")
        if alias["id"] == "task_detail":
            require("/workspace/tasks/" in text and "encodeURIComponent(taskId)" in text, "task detail alias must preserve task id")
        if alias["id"] == "run_ledger":
            require('redirect("/workspace/runs")' in text, "run ledger alias must redirect to /workspace/runs")
        if alias["id"] == "run_detail":
            require("/workspace/runs/" in text and "encodeURIComponent(runId)" in text, "run detail alias must preserve run id")

    decision_text = (ROOT / "docs" / "UI_ROUTE_NAMING_DECISION.json").read_text(encoding="utf-8")
    matrix_text = (ROOT / "docs" / "UI_API_PARITY_MATRIX.json").read_text(encoding="utf-8")
    readiness_text = (ROOT / "scripts" / "commercial_migration_readiness.py").read_text(encoding="utf-8")
    require(CONTRACT_ID in decision_text, "route naming decision must reference the legacy alias contract")
    require(CONTRACT_ID in matrix_text, "UI/API matrix must reference the legacy alias contract")
    require(CONTRACT_ID in readiness_text, "readiness checker must require the legacy alias contract")


def redirect_location(base_url: str, path: str) -> tuple[int, str]:
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(base_url.rstrip("/") + path, method="GET")
    try:
        with opener.open(request, timeout=10) as response:
            return response.status, response.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Location", "")


def wait_for_redirect(base_url: str, legacy_path: str, target_path: str) -> tuple[int, str]:
    deadline = time.time() + 30
    last: tuple[int, str] = (0, "")
    while time.time() < deadline:
        last = redirect_location(base_url, legacy_path)
        status, location = last
        if status in {307, 308} and location.endswith(target_path):
            return last
        time.sleep(0.5)
    raise AssertionError(f"Timed out waiting for {legacy_path} to redirect to {target_path}; last={last}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Next.js legacy route alias smoke.")
    parser.add_argument("--next-port", type=int, default=0)
    args = parser.parse_args()

    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "error": "npx is required for Next.js legacy alias smoke"}, indent=2), file=sys.stderr)
        return 1

    assert_static_aliases()
    next_port = args.next_port or free_port()
    next_base = f"http://127.0.0.1:{next_port}"
    processes: list[subprocess.Popen[str]] = []

    try:
        next_env = os.environ.copy()
        next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
        processes.append(next_proc)
        wait_http(f"{next_base}/")

        checked = []
        for alias in ALIASES:
            status, location = wait_for_redirect(next_base, alias["legacy_path"], alias["target_path"])
            checked.append({
                "id": alias["id"],
                "legacy_path": alias["legacy_path"],
                "target_path": alias["target_path"],
                "status": status,
                "location": location,
            })

        print(json.dumps({
            "ok": True,
            "contract": CONTRACT_ID,
            "next_base": next_base,
            "aliases": checked,
            "legacy_aliases_preserved": True,
            "task_run_retirement_action": "executed_workspace_redirect",
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        for proc in reversed(processes):
            stop_process(proc)
        run(["bash", "-lc", f"lsof -tiTCP:{next_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        restore_next_env()


if __name__ == "__main__":
    raise SystemExit(main())
