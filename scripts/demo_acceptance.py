#!/usr/bin/env python3
"""Lightweight demo acceptance checks for AgentOps MIS v1.2.1."""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "agentops_mis.db"


def request_json(base_url: str, method: str, path: str, body: dict | None = None, timeout: int = 10) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {"error": str(exc)}
        return exc.code, payload


def reachable(base_url: str) -> bool:
    try:
        status, _ = request_json(base_url, "GET", "/api/dashboard/metrics", timeout=2)
        return status == 200
    except (URLError, TimeoutError, OSError):
        return False


def start_server(base_url: str) -> subprocess.Popen | None:
    if reachable(base_url):
        return None
    proc = subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(40):
        if reachable(base_url):
            return proc
        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"server exited early: {stderr[-1000:]}")
        time.sleep(0.25)
    proc.terminate()
    raise RuntimeError("server did not become reachable on time")


def sqlite_counts() -> dict:
    if not DB_PATH.exists():
        return {}
    with sqlite3.connect(DB_PATH) as conn:
        return {
            "agents": conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0],
            "tasks": conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
            "runs": conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
            "tool_calls": conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0],
            "memories": conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
            "audit_logs": conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0],
            "runtime_connectors": conn.execute("SELECT COUNT(*) FROM runtime_connectors").fetchone()[0],
            "bases": conn.execute("SELECT COUNT(*) FROM bases").fetchone()[0],
            "template_packages": conn.execute("SELECT COUNT(*) FROM template_packages").fetchone()[0],
        }


def assert_true(checks: list[dict], name: str, ok: bool, detail=None) -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--start-server", action="store_true", help="Start server.py if the API is not reachable.")
    args = parser.parse_args()

    proc = None
    if args.start_server:
        proc = start_server(args.base_url)

    checks: list[dict] = []
    try:
        endpoints = [
            ("GET", "/api/dashboard/metrics", None),
            ("GET", "/api/integrations/openclaw/status", None),
            ("GET", "/api/integrations/hermes/status", None),
            ("GET", "/api/integrations/hermes/models", None),
            ("GET", "/api/integrations/notion/status", None),
            ("GET", "/api/runtime-connectors", None),
            ("GET", "/api/bases", None),
            ("GET", "/api/connectors", None),
            ("GET", "/api/template-packages", None),
            ("POST", "/api/integrations/notion/preview", {}),
            ("POST", "/api/integrations/notion/dry-run-export", {}),
            ("POST", "/api/integrations/hermes/cli-probe", {}),
            ("POST", "/api/migration/preview", {}),
        ]
        payloads = {}
        for method, path, body in endpoints:
            status, payload = request_json(args.base_url, method, path, body)
            payloads[path] = payload
            if isinstance(payload, dict):
                shape = {"status": status, "keys": sorted(payload.keys())[:12]}
            elif isinstance(payload, list):
                shape = {"status": status, "items": len(payload)}
            else:
                shape = {"status": status, "type": type(payload).__name__}
            assert_true(checks, f"{method} {path}", 200 <= status < 300, shape)

        metrics = payloads["/api/dashboard/metrics"]
        assert_true(checks, "dashboard exposes runtime health", bool(metrics.get("runtime_health")), metrics.get("runtime_health"))
        assert_true(checks, "dashboard exposes agent performance", bool(metrics.get("agent_performance_summary")), len(metrics.get("agent_performance_summary", [])))

        hermes = payloads["/api/integrations/hermes/status"]
        assert_true(checks, "hermes unavailable is non-fatal", "api_listening" in hermes and "agnesfallback" in hermes, hermes.get("agnesfallback"))

        notion = payloads["/api/integrations/notion/status"]
        assert_true(checks, "notion defaults safe", notion.get("dry_run_default") is True and notion.get("writeback_allowed") is False, notion)

        bases = payloads["/api/bases"]
        assert_true(checks, "bases available", len(bases.get("bases", [])) >= 5, len(bases.get("bases", [])))

        counts = sqlite_counts()
        assert_true(checks, "audit log exists", counts.get("audit_logs", 0) > 0, counts)
        assert_true(checks, "runtime connector rows exist", counts.get("runtime_connectors", 0) >= 3, counts)
        assert_true(checks, "template package rows exist", counts.get("template_packages", 0) >= 4, counts)

        ok = all(item["ok"] for item in checks)
        print(json.dumps({"ok": ok, "base_url": args.base_url, "checks": checks, "counts": counts}, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
