#!/usr/bin/env python3
"""Verify Next.js renders a read-only Pixel Office floor from live MIS ledgers."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "nextjs_pixel_office_floor_v1"

sys.path.insert(0, str(SCRIPTS))

from nextjs_playwright_snapshot_smoke import (  # noqa: E402
    free_port,
    leaked_secret,
    restore_next_env,
    run,
    start_process,
    wait_http,
)


def http_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def http_text_status(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=90) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": "npx is required"}, indent=2), file=sys.stderr)
        return 1

    processes: list[subprocess.Popen[str]] = []
    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-pixel-office-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            reset_env = os.environ.copy()
            reset_env.pop("AGENTOPS_API_KEY", None)
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = os.environ.copy()
            api_env.pop("AGENTOPS_API_KEY", None)
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env.pop("AGENTOPS_API_KEY", None)
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace/pixel-office")

            status, html = http_text_status(f"{next_base}/workspace/pixel-office")
            require(status == 200, f"Pixel Office page returned {status}")
            expected = [
                "Pixel Office",
                "Pixel Operating Map",
                "read-only route contract",
                "commercial-safe geometry",
                "no Star Office assets",
                "live runtime disabled",
                "Owner dispatch workflow",
                "template intake /workspace/dispatch",
                "worker dispatch /workspace/dispatch/customer-worker",
                "prepared actions /workspace/dispatch",
                "approval wall /workspace/approvals",
                "delivery reports /workspace/reports",
                "evidence ledger /workspace/runs",
                "Control Tower",
                "Dispatch Hall",
                "Approval Gate",
                "Audit Vault",
                "/workspace/dispatch",
                "/workspace/tasks",
                "/workspace/runs",
            ]
            missing = [text for text in expected if text not in html]
            require(not missing, f"Pixel Office page missed expected text/routes: {missing}")

            agents = http_json(f"{next_base}/api/mis/agents")
            tasks = http_json(f"{next_base}/api/mis/tasks")
            runs = http_json(f"{next_base}/api/mis/runs")
            require(isinstance(agents, list) and len(agents) >= 1, "Pixel Office MIS proxy agents readback is empty")
            require(isinstance(tasks, list) and len(tasks) >= 1, "Pixel Office MIS proxy tasks readback is empty")
            require(isinstance(runs, list), "Pixel Office MIS proxy runs readback is not a list")

            transcript = json.dumps({"html": html, "agents": agents[:3], "tasks": tasks[:3], "runs": runs[:3]}, ensure_ascii=False, sort_keys=True)
            require(not leaked_secret(transcript), "Pixel Office page or proxy readback leaked token-like material")

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "route": "/workspace/pixel-office",
                "api_readback": ["/api/mis/agents", "/api/mis/tasks", "/api/mis/runs"],
                "zones": ["Control Tower", "Dispatch Hall", "Approval Gate", "Audit Vault"],
                "read_only": True,
                "owner_dispatch_workflow": True,
                "live_runtime_enabled": False,
                "secret_leaked": False,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        run(["bash", "-lc", f"lsof -tiTCP:{next_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["bash", "-lc", f"lsof -tiTCP:{api_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["rm", "-rf", str(NEXT_APP / ".next")], timeout=10)
        restore_next_env()


if __name__ == "__main__":
    raise SystemExit(main())
