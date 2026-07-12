#!/usr/bin/env python3
"""Run the local AgentOps MIS backend, UI, and bounded worker processes."""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui" / "start-building-app"
CLI = ROOT / "scripts" / "agentops"
LIVE_ADAPTERS = {"hermes", "openclaw"}


def request_shutdown(_signum, _frame) -> None:
    raise KeyboardInterrupt


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def gateway_ready(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/agent-gateway/status", timeout=1) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return response.status == 200 and payload.get("provider") == "agent_gateway"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def wait_ready(check, label: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if check():
            return
        time.sleep(0.2)
    raise RuntimeError(f"{label} did not become ready")


def terminate_processes(processes: list[tuple[str, subprocess.Popen]]) -> None:
    for _label, process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    for _label, process in reversed(processes):
        if process.poll() is not None:
            continue
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def worker_command(adapter: str, poll_interval: float, confirm_live_workers: bool) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "agentops_mis_cli.worker",
        "--adapter",
        adapter,
        "--agent-id",
        f"agt_worker_local_stack_{adapter}",
        "--poll-interval",
        str(poll_interval),
        "--max-tasks",
        "0",
        "--continue-on-error",
        "--write-state",
        "--jsonl-log",
    ]
    if adapter in LIVE_ADAPTERS and confirm_live_workers:
        command.append("--confirm-run")
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the local AgentOps MIS backend, UI, and worker loop.")
    parser.add_argument("--install-ui", action="store_true", help="Run npm ci --prefer-offline if UI dependencies are missing.")
    parser.add_argument("--production-ui", action="store_true", help="Serve the built React UI from the backend instead of starting Vite.")
    parser.add_argument("--build-ui", action="store_true", help="Build the React UI before starting; implies --production-ui.")
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8787)
    parser.add_argument("--ui-host", default="127.0.0.1")
    parser.add_argument("--ui-port", type=int, default=19001)
    parser.add_argument("--no-ui", action="store_true", help="Start the backend and workers without the browser UI.")
    parser.add_argument("--worker", action="append", choices=["mock", "hermes", "openclaw"], help="Worker adapter to start. Repeat for multiple workers; defaults to mock.")
    parser.add_argument("--no-workers", action="store_true", help="Do not start repo-local worker processes.")
    parser.add_argument("--confirm-live-workers", action="store_true", help="Explicitly allow requested Hermes/OpenClaw workers to execute live tasks.")
    parser.add_argument("--worker-poll-interval", type=float, default=5.0)
    parser.add_argument("--configure-cli", action="store_true", help="Explicitly update the saved CLI base URL/workspace for this local stack.")
    args = parser.parse_args()
    if args.build_ui:
        args.production_ui = True
    if args.no_ui and args.production_ui:
        parser.error("--no-ui cannot be combined with --production-ui or --build-ui")
    signal.signal(signal.SIGTERM, request_shutdown)

    backend_url = f"http://{args.backend_host}:{args.backend_port}"
    workers = [] if args.no_workers else list(dict.fromkeys(args.worker or ["mock"]))
    live_workers = sorted(set(workers) & LIVE_ADAPTERS)
    if live_workers and not args.confirm_live_workers:
        parser.error(
            "Hermes/OpenClaw workers require --confirm-live-workers; "
            "use --worker mock or --no-workers for a non-live stack"
        )
    if args.backend_host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("run_local_stack.py is local-only; keep --backend-host on loopback")

    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = backend_url
    env["AGENTOPS_LOCAL_DEMO_DEFAULT_URL"] = backend_url
    env["AGENTOPS_WORKSPACE_ID"] = env.get("AGENTOPS_WORKSPACE_ID", "local-demo")
    env["VITE_AGENTOPS_PROXY_TARGET"] = backend_url
    processes: list[tuple[str, subprocess.Popen]] = []

    try:
        if args.production_ui:
            if not UI_DIR.exists():
                raise RuntimeError(f"missing UI directory: {UI_DIR}")
            if not (UI_DIR / "node_modules").exists():
                if args.install_ui:
                    subprocess.run(["npm", "ci", "--prefer-offline"], cwd=UI_DIR, env=env, check=True)
                else:
                    raise RuntimeError("UI dependencies missing. Add --install-ui before building the production UI")
            if args.build_ui:
                subprocess.run(["npm", "run", "build"], cwd=UI_DIR, env=env, check=True)
            if not (UI_DIR / "dist" / "index.html").is_file():
                raise RuntimeError("production UI missing. Run with --build-ui")
        if port_open(args.backend_port, args.backend_host):
            if args.production_ui:
                raise RuntimeError(
                    f"port {args.backend_port} is already in use; stop the existing backend before starting production UI mode"
                )
            if not gateway_ready(backend_url):
                raise RuntimeError(f"port {args.backend_port} is occupied by a non-AgentOps service")
            print(f"backend already running at {backend_url}/dashboard")
        else:
            backend_command = [sys.executable, "server.py", "--host", args.backend_host, "--port", str(args.backend_port)]
            if args.production_ui:
                backend_command.extend(["--ui-dist", str(UI_DIR / "dist")])
            backend = subprocess.Popen(
                backend_command,
                cwd=ROOT,
                env=env,
            )
            processes.append(("backend", backend))
            wait_ready(lambda: gateway_ready(backend_url), f"backend on {backend_url}")

        if args.configure_cli:
            configured = subprocess.run(
                [str(CLI), "login", "--base-url", backend_url, "--workspace-id", env["AGENTOPS_WORKSPACE_ID"]],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if configured.returncode != 0:
                raise RuntimeError("failed to update local CLI connection; no token output was retained")

        if not args.no_ui and not args.production_ui:
            if not UI_DIR.exists():
                raise RuntimeError(f"missing UI directory: {UI_DIR}")
            if not (UI_DIR / "node_modules").exists():
                if args.install_ui:
                    subprocess.run(["npm", "ci", "--prefer-offline"], cwd=UI_DIR, env=env, check=True)
                else:
                    raise RuntimeError("UI dependencies missing. Run: python3 scripts/run_local_stack.py --install-ui")
            if port_open(args.ui_port, args.ui_host):
                print(f"ui already running at http://{args.ui_host}:{args.ui_port}/")
            else:
                ui = subprocess.Popen(
                    ["npm", "run", "dev", "--", "--host", args.ui_host, "--port", str(args.ui_port)],
                    cwd=UI_DIR,
                    env=env,
                )
                processes.append(("ui", ui))
                wait_ready(lambda: port_open(args.ui_port, args.ui_host), f"UI on {args.ui_host}:{args.ui_port}")

        for adapter in workers:
            worker_env = env.copy()
            worker_env["AGENTOPS_AGENT_ID"] = f"agt_worker_local_stack_{adapter}"
            worker = subprocess.Popen(worker_command(adapter, args.worker_poll_interval, args.confirm_live_workers), cwd=ROOT, env=worker_env)
            processes.append((f"worker:{adapter}", worker))
            time.sleep(0.2)
            if worker.poll() is not None:
                raise RuntimeError(f"{adapter} worker exited during startup with code {worker.returncode}")

        print("")
        print("AgentOps MIS local stack is running:")
        print(f"  backend: http://{args.backend_host}:{args.backend_port}/dashboard")
        if args.production_ui:
            print(f"  workspace: {backend_url}/workspace")
            print(f"  workers:   {backend_url}/workspace/workers")
            print("  UI mode:   production same-origin")
        elif not args.no_ui:
            print(f"  workspace: http://{args.ui_host}:{args.ui_port}/workspace")
            print(f"  workers:   http://{args.ui_host}:{args.ui_port}/workspace/workers")
            print("  UI mode:   Vite development")
        print(f"  adapters:  {', '.join(workers) if workers else 'none'}")
        print(f"  live mode: {'confirmed' if live_workers else 'off'}")
        if not args.configure_cli:
            print(f"  CLI check: AGENTOPS_BASE_URL={backend_url} agentops doctor")
            print(f"  save URL:  agentops login --base-url {backend_url} --workspace-id {env['AGENTOPS_WORKSPACE_ID']}")
        print("")
        print("Press Ctrl-C here to stop processes started by this script.")

        while processes:
            for label, process in list(processes):
                returncode = process.poll()
                if returncode is None:
                    continue
                if returncode != 0:
                    raise RuntimeError(f"{label} exited with code {returncode}")
                processes.remove((label, process))
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping AgentOps MIS local stack")
    finally:
        terminate_processes(processes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
