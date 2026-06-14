#!/usr/bin/env python3
"""Run the local AgentOps MIS backend and Figma UI preview together."""
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "ui" / "start-building-app"


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex((host, port)) == 0


def wait_port(port: int, label: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if port_open(port):
            return
        time.sleep(0.2)
    raise RuntimeError(f"{label} did not become ready on 127.0.0.1:{port}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Start local AgentOps MIS backend and UI.")
    parser.add_argument("--install-ui", action="store_true", help="Run npm install --prefer-offline if UI dependencies are missing.")
    args = parser.parse_args()

    procs: list[subprocess.Popen] = []

    if not port_open(8787):
        backend = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT)
        procs.append(backend)
        wait_port(8787, "backend")
    else:
        print("backend already running at http://127.0.0.1:8787/dashboard")

    if not UI_DIR.exists():
        raise RuntimeError(f"missing UI directory: {UI_DIR}")
    if not (UI_DIR / "node_modules").exists():
        if args.install_ui:
            subprocess.run(["npm", "install", "--prefer-offline"], cwd=UI_DIR, check=True)
        else:
            raise RuntimeError("UI dependencies missing. Run: python3 scripts/run_local_stack.py --install-ui")

    if not port_open(5173):
        ui = subprocess.Popen(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173"], cwd=UI_DIR)
        procs.append(ui)
        wait_port(5173, "ui")
    else:
        print("ui already running at http://127.0.0.1:5173/")

    print("")
    print("AgentOps MIS local stack is running:")
    print("  backend demo: http://127.0.0.1:8787/dashboard")
    print("  beta UI:      http://127.0.0.1:5173/")
    print("")
    print("Press Ctrl-C here to stop processes started by this script.")

    try:
        while procs:
            for proc in list(procs):
                if proc.poll() is not None:
                    procs.remove(proc)
                    if proc.returncode:
                        return proc.returncode
            time.sleep(0.5)
    except KeyboardInterrupt:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
