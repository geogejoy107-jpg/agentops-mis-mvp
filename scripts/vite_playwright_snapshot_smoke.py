#!/usr/bin/env python3
"""Browser snapshot smoke for the canonical Vite workspace UI."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
VITE_APP = ROOT / "ui" / "start-building-app"
ARTIFACT_SAMPLE_PATHS = [
    ROOT / "artifacts" / "sample_export_runs.json",
    ROOT / "artifacts" / "sample_export_memories.json",
]

sys.path.insert(0, str(SCRIPTS))

from nextjs_playwright_snapshot_smoke import (  # noqa: E402
    PWCLI,
    free_port,
    http_json,
    leaked_secret,
    playwright,
    require,
    run,
    seed_customer_project_fixture,
    start_process,
    wait_http,
)


Expectation = str | tuple[str, ...]

VITE_ROUTE_EXPECTATIONS: list[tuple[str, list[Expectation]]] = [
    ("/workspace", ["Workspace Home", "MIS live cockpit", "Pending Approvals"]),
    ("/workspace/pixel-office", [("Pixel Office", "像素"), ("Operations Bar", "运行状态栏"), ("Customer task templates", "客户任务模板")]),
    ("/workspace/tasks", [("My Tasks", "我的任务"), ("Refresh live tasks", "刷新实时任务")]),
    ("/workspace/agents", [("AI Employees", "AI 员工"), ("Worker Fleet Console", "Worker Fleet 控制台"), ("Customer task dispatch", "客户任务派发")]),
    ("/workspace/approvals", [("Approvals Inbox", "审批收件箱"), ("Pending Approval", "待审批"), ("Approve", "批准")]),
    ("/workspace/memory", ["Memory Library", "candidate"]),
    ("/workspace/reports", [("Reports", "报告"), ("Customer delivery board", "客户交付看板")]),
    ("/admin/runs", [("Run Ledger", "运行账本"), ("Run", "运行")]),
    ("/admin/audit", ["Audit Center", "Chain intact"]),
]


def save_sample_exports() -> dict[Path, bytes | None]:
    saved: dict[Path, bytes | None] = {}
    for path in ARTIFACT_SAMPLE_PATHS:
        saved[path] = path.read_bytes() if path.exists() else None
    return saved


def restore_sample_exports(saved: dict[Path, bytes | None]) -> None:
    for path, content in saved.items():
        if content is None:
            path.unlink(missing_ok=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def missing_expectations(text: str, expected: Iterable[Expectation]) -> list[str]:
    missing: list[str] = []
    for item in expected:
        if isinstance(item, tuple):
            if not any(option in text for option in item):
                missing.append(" or ".join(item))
            continue
        if item not in text:
            missing.append(item)
    return missing


def snapshot_route(base_url: str, path: str, expected: list[Expectation], env: dict[str, str]) -> dict:
    target = base_url.rstrip("/") + path
    goto = playwright(env, "goto", target)
    require(goto.returncode == 0, f"Playwright goto failed for {path}: {goto.stderr or goto.stdout}")
    time.sleep(1.0)

    snapshot = playwright(env, "snapshot")
    require(snapshot.returncode == 0, f"Playwright snapshot failed for {path}: {snapshot.stderr or snapshot.stdout}")
    text = snapshot.stdout + snapshot.stderr
    missing = missing_expectations(text, expected)
    require(not missing, f"Vite snapshot for {path} missed expected text: {missing}")
    require(not leaked_secret(text), f"Vite snapshot for {path} leaked token-like material")
    return {
        "path": path,
        "expected": [" / ".join(item) if isinstance(item, tuple) else item for item in expected],
        "snapshot_chars": len(text),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Vite Playwright snapshot smoke.")
    parser.add_argument("--api-port", type=int, default=0)
    parser.add_argument("--vite-port", type=int, default=0)
    args = parser.parse_args()

    if not PWCLI.exists():
        print(json.dumps({"ok": False, "error": f"missing Playwright wrapper: {PWCLI}"}, indent=2), file=sys.stderr)
        return 1
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "error": "npx is required for Playwright CLI wrapper"}, indent=2), file=sys.stderr)
        return 1

    api_port = args.api_port or free_port()
    vite_port = args.vite_port or free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    vite_base = f"http://127.0.0.1:{vite_port}"
    session = f"agentops-vite-parity-{uuid.uuid4().hex[:8]}"
    processes: list[subprocess.Popen[str]] = []
    saved_exports = save_sample_exports()

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-vite-pw-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            reset_env = os.environ.copy()
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")
            project_id = seed_customer_project_fixture(db_path)

            api_env = os.environ.copy()
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            vite_env = os.environ.copy()
            vite_env["VITE_AGENTOPS_PROXY_TARGET"] = api_base
            vite_proc = start_process(
                ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(vite_port)],
                cwd=VITE_APP,
                env=vite_env,
            )
            processes.append(vite_proc)
            wait_http(f"{vite_base}/workspace")

            proxy_metrics = http_json(f"{vite_base}/mis-api/dashboard/metrics")
            require(isinstance(proxy_metrics, dict), f"Vite proxy metrics returned non-object: {proxy_metrics!r}")

            pw_env = os.environ.copy()
            pw_env["PLAYWRIGHT_CLI_SESSION"] = session
            opened = playwright(pw_env, "open", f"{vite_base}/workspace")
            require(opened.returncode == 0, f"Playwright open failed: {opened.stderr or opened.stdout}")
            resized = playwright(pw_env, "resize", "1365", "900")
            require(resized.returncode == 0, f"Playwright resize failed: {resized.stderr or resized.stdout}")

            routes = [
                *VITE_ROUTE_EXPECTATIONS,
                (
                    f"/workspace/customer-projects/{project_id}/report",
                    [("Customer project delivery report", "客户项目交付报告"), project_id, ("Approvals", "审批")],
                ),
            ]
            snapshots = [snapshot_route(vite_base, path, expected, pw_env) for path, expected in routes]
            proxy_checks = {
                "agents": len(http_json(f"{vite_base}/mis-api/agents")),
                "tasks": len(http_json(f"{vite_base}/mis-api/tasks")),
                "approvals": len(http_json(f"{vite_base}/mis-api/approvals")),
                "memories": len(http_json(f"{vite_base}/mis-api/memories")),
                "customer_project_fixture": project_id,
                "metrics_agents_total": proxy_metrics.get("agents_total"),
            }

            try:
                playwright(pw_env, "close", timeout=10)
            except subprocess.TimeoutExpired:
                playwright(pw_env, "kill-all", timeout=20)
            payload = {
                "ok": True,
                "contract": "vite_browser_snapshot_parity_v1",
                "api_base": api_base,
                "vite_base": vite_base,
                "routes": snapshots,
                "proxy_checks": proxy_checks,
                "secret_leaked": False,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        run(["bash", "-lc", f"lsof -tiTCP:{vite_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["bash", "-lc", f"lsof -tiTCP:{api_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["rm", "-rf", str(VITE_APP / "dist")], timeout=10)
        restore_sample_exports(saved_exports)


if __name__ == "__main__":
    raise SystemExit(main())
