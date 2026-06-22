#!/usr/bin/env python3
"""Browser snapshot smoke for the Next.js parity track.

The script starts an isolated MIS API provider and Next.js dev server, then uses
the Codex Playwright CLI wrapper to capture accessibility snapshots for the
current parity routes. It intentionally performs read-only navigation and API
proxy checks only.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEXT_APP = ROOT / "ui" / "next-app"
PWCLI = Path.home() / ".codex" / "skills" / "playwright" / "scripts" / "playwright_cli.sh"
NEXT_ENV = NEXT_APP / "next-env.d.ts"

ROUTES = [
    ("/workspace", ["Workspace control plane", "Active tasks", "Pending approval queue"]),
    ("/workspace/agents", ["Agents", "Production security", "Adapter readiness"]),
    ("/workspace/tasks", ["Tasks", "running", "planned"]),
    ("/workspace/runs", ["Run Ledger", "Run", "Status"]),
    ("/workspace/approvals", ["Approvals", "Pending approval", "Decision history"]),
    ("/workspace/memory", ["Memory", "candidate", "approved"]),
    ("/workspace/audit", ["Audit", "audit events", "Actor"]),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def start_process(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def wait_http(url: str, timeout_sec: int = 45) -> None:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def http_json(url: str) -> object:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def restore_next_env() -> None:
    if not NEXT_ENV.exists():
        return
    text = NEXT_ENV.read_text(encoding="utf-8")
    text = text.replace('import "./.next/dev/types/routes.d.ts";', 'import "./.next/types/routes.d.ts";')
    NEXT_ENV.write_text(text, encoding="utf-8")


def leaked_secret(text: str) -> bool:
    markers = ["Authorization: " + "Bearer", "agtok" + "_", "agtsess" + "_", "sk" + "-", "ntn" + "_"]
    return any(marker in text for marker in markers)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def playwright(env: dict[str, str], *args: str, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return run(["bash", str(PWCLI), *args], env=env, timeout=timeout)


def snapshot_route(base_url: str, path: str, expected: list[str], env: dict[str, str]) -> dict:
    target = base_url.rstrip("/") + path
    goto = playwright(env, "goto", target)
    require(goto.returncode == 0, f"Playwright goto failed for {path}: {goto.stderr or goto.stdout}")
    time.sleep(1.0)

    snapshot = playwright(env, "snapshot")
    require(snapshot.returncode == 0, f"Playwright snapshot failed for {path}: {snapshot.stderr or snapshot.stdout}")
    text = snapshot.stdout + snapshot.stderr
    missing = [item for item in expected if item not in text]
    require(not missing, f"Snapshot for {path} missed expected text: {missing}")
    require(not leaked_secret(text), f"Snapshot for {path} leaked token-like material")
    return {"path": path, "expected": expected, "snapshot_chars": len(text)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Next.js Playwright snapshot smoke.")
    parser.add_argument("--api-port", type=int, default=0)
    parser.add_argument("--next-port", type=int, default=0)
    args = parser.parse_args()

    if not PWCLI.exists():
        print(json.dumps({"ok": False, "error": f"missing Playwright wrapper: {PWCLI}"}, indent=2), file=sys.stderr)
        return 1
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "error": "npx is required for Playwright CLI wrapper"}, indent=2), file=sys.stderr)
        return 1

    api_port = args.api_port or free_port()
    next_port = args.next_port or free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"
    session = f"agentops-next-parity-{uuid.uuid4().hex[:8]}"
    processes: list[subprocess.Popen[str]] = []

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-pw-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            reset_env = os.environ.copy()
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = os.environ.copy()
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace")

            pw_env = os.environ.copy()
            pw_env["PLAYWRIGHT_CLI_SESSION"] = session
            opened = playwright(pw_env, "open", f"{next_base}/workspace")
            require(opened.returncode == 0, f"Playwright open failed: {opened.stderr or opened.stdout}")
            resized = playwright(pw_env, "resize", "1365", "900")
            require(resized.returncode == 0, f"Playwright resize failed: {resized.stderr or resized.stdout}")

            snapshots = [snapshot_route(next_base, path, expected, pw_env) for path, expected in ROUTES]
            proxy_checks = {
                "agents": len(http_json(f"{next_base}/api/mis/agents")),
                "tasks": len(http_json(f"{next_base}/api/mis/tasks")),
                "memories": len(http_json(f"{next_base}/api/mis/memories")),
                "security_status": http_json(f"{next_base}/api/mis/security/production-readiness").get("status"),
                "worker_status": http_json(f"{next_base}/api/mis/workers/status").get("status"),
            }

            try:
                playwright(pw_env, "close", timeout=10)
            except subprocess.TimeoutExpired:
                playwright(pw_env, "kill-all", timeout=20)
            payload = {
                "ok": True,
                "api_base": api_base,
                "next_base": next_base,
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
        run(["bash", "-lc", f"lsof -tiTCP:{next_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["bash", "-lc", f"lsof -tiTCP:{api_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["rm", "-rf", str(NEXT_APP / ".next")], timeout=10)
        restore_next_env()


if __name__ == "__main__":
    raise SystemExit(main())
