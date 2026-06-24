#!/usr/bin/env python3
"""Verify the split Next.js Control Tower parity surface."""
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
CONTRACT_ID = "nextjs_control_tower_parity_v1"

sys.path.insert(0, str(SCRIPTS))

from nextjs_playwright_snapshot_smoke import (  # noqa: E402
    free_port,
    leaked_secret,
    restore_next_env,
    run,
    snapshot_route,
    start_process,
    wait_http,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def http_json_status(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}


def stop_processes(processes: list[subprocess.Popen[str]]) -> list[str]:
    logs: list[str] = []
    for proc in reversed(processes):
        if proc.poll() is None:
            proc.terminate()
        try:
            output, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate(timeout=5)
        if output:
            logs.append(output[-2000:])
    return logs


def assert_no_secret(label: str, payload: Any) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, sort_keys=True)
    require("session_token" not in text, f"{label} leaked session_token")
    require("token_hash" not in text and "session_hash" not in text, f"{label} leaked token/session hash")
    require(not leaked_secret(text), f"{label} leaked token-like material")


def assert_same_value(label: str, direct: dict[str, Any], proxied: dict[str, Any], key: str) -> None:
    require(direct.get(key) == proxied.get(key), f"{label} mismatch for {key}: {direct.get(key)!r} != {proxied.get(key)!r}")


def assert_dashboard_parity(direct: dict[str, Any], proxied: dict[str, Any]) -> None:
    for key in ["agents_total", "agents_running", "tasks_completed_total", "pending_approvals", "stale_or_due_memories"]:
        assert_same_value("dashboard metrics", direct, proxied, key)
    require(isinstance(proxied.get("runtime_health"), list) and proxied["runtime_health"], "dashboard proxy missing runtime health")
    require(isinstance(proxied.get("task_status_distribution"), list) and proxied["task_status_distribution"], "dashboard proxy missing task status distribution")
    require(isinstance(proxied.get("top_cost_agents"), list), "dashboard proxy missing cost leaders")
    require(isinstance(proxied.get("openclaw_import"), dict), "dashboard proxy missing OpenClaw import readback")


def sqlite_env(db_path: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    for key in [
        "AGENTOPS_POSTGRES_DSN",
        "AGENTOPS_ENABLE_POSTGRES_STORAGE",
        "AGENTOPS_POSTGRES_READ_ONLY_HTTP",
        "AGENTOPS_POSTGRES_WRITE_HTTP",
        "DATABASE_URL",
    ]:
        env.pop(key, None)
    env["AGENTOPS_DB_PATH"] = db_path
    env["AGENTOPS_STORAGE_BACKEND"] = "sqlite"
    return env


def main() -> int:
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": "npx is required"}, indent=2), file=sys.stderr)
        return 1

    processes: list[subprocess.Popen[str]] = []
    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"
    transcript: list[Any] = []

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-control-tower-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            reset_env = sqlite_env(db_path)
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = sqlite_env(db_path)
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env.pop("AGENTOPS_API_KEY", None)
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace")

            direct_dashboard_status, direct_dashboard = http_json_status("GET", f"{api_base}/api/dashboard/metrics")
            proxy_dashboard_status, proxy_dashboard = http_json_status("GET", f"{next_base}/api/mis/dashboard/metrics")
            require(direct_dashboard_status == 200, f"direct dashboard failed: {direct_dashboard_status} {direct_dashboard}")
            require(proxy_dashboard_status == 200, f"Next dashboard proxy failed: {proxy_dashboard_status} {proxy_dashboard}")
            assert_dashboard_parity(direct_dashboard, proxy_dashboard)

            proxy_agents_status, proxy_agents = http_json_status("GET", f"{next_base}/api/mis/agents")
            require(proxy_agents_status == 200 and isinstance(proxy_agents, list) and proxy_agents, f"Next agents proxy failed: {proxy_agents_status} {proxy_agents}")

            proxy_security_status, proxy_security = http_json_status("GET", f"{next_base}/api/mis/security/production-readiness")
            require(proxy_security_status == 200, f"Next production readiness proxy failed: {proxy_security_status} {proxy_security}")
            require((proxy_security.get("safety") or {}).get("read_only") is True, f"production readiness must be read-only: {proxy_security}")
            require((proxy_security.get("safety") or {}).get("live_execution_performed") is False, f"production readiness unexpectedly performed live execution: {proxy_security}")

            proxy_local_status, proxy_local = http_json_status("GET", f"{next_base}/api/mis/local/readiness")
            require(proxy_local_status == 200, f"Next local readiness proxy failed: {proxy_local_status} {proxy_local}")
            require(proxy_local.get("operation") == "local_readiness", f"local readiness operation mismatch: {proxy_local}")
            require(proxy_local.get("token_omitted") is True, f"local readiness token omission missing: {proxy_local}")

            proxy_storage_status, proxy_storage = http_json_status("GET", f"{next_base}/api/mis/storage/backend-status")
            require(proxy_storage_status == 200, f"Next storage backend proxy failed: {proxy_storage_status} {proxy_storage}")
            require(proxy_storage.get("active_backend") == "sqlite", f"Free Local storage backend should stay sqlite: {proxy_storage}")
            postgres_status = proxy_storage.get("postgres") or {}
            require(postgres_status.get("server_backend_routable") is False, f"Free Local storage backend should not route Postgres writes: {proxy_storage}")
            require(proxy_storage.get("token_omitted") is True, f"storage backend route must omit token material: {proxy_storage}")

            proxy_entitlements_status, proxy_entitlements = http_json_status("GET", f"{next_base}/api/mis/commercial/entitlements")
            require(proxy_entitlements_status == 200, f"Next commercial entitlements proxy failed: {proxy_entitlements_status} {proxy_entitlements}")
            require(proxy_entitlements.get("edition") == "free_local", f"control tower default edition should stay free_local: {proxy_entitlements}")
            entitlement_gates = {
                str(gate.get("capability")): gate
                for gate in proxy_entitlements.get("gates") or []
                if isinstance(gate, dict)
            }
            approval_gate = entitlement_gates.get("approval_policies") or {}
            require(approval_gate.get("enabled") is False, f"Free Local approval_policies gate should be disabled: {approval_gate}")
            require(approval_gate.get("required_edition") == "team_governance", f"approval_policies required edition mismatch: {approval_gate}")
            require(approval_gate.get("enforcement") == "fail_closed", f"approval_policies should fail closed: {approval_gate}")
            require((proxy_entitlements.get("safety") or {}).get("billing_call_performed") is False, f"entitlements should not call billing: {proxy_entitlements}")
            require((proxy_entitlements.get("safety") or {}).get("live_execution_performed") is False, f"entitlements should not execute live work: {proxy_entitlements}")
            require(proxy_entitlements.get("token_omitted") is True, f"entitlements should omit tokens: {proxy_entitlements}")

            pw_env = os.environ.copy()
            workspace_snapshot = snapshot_route(next_base, "/workspace", [
                "Workspace control plane",
                "Control Tower split proof",
                "/dashboard/metrics cockpit readback",
                "/workspace/agents agent performance drilldown",
                "/workspace/governance production and session governance",
                "/workspace/deployment BYOC storage and recovery gates",
                "Runtime health",
                "OpenClaw import readback",
                "Task status distribution",
                "Cost leaders",
                "route retirement blocked",
            ], pw_env)
            governance_snapshot = snapshot_route(next_base, "/workspace/governance", [
                "Governance",
                "Production readiness",
                "Workspace and RBAC",
                "Session governance",
                "Remote enrollment approval",
                "approval_policies",
                "fail closed",
                "Audit evidence",
                "raw ids omitted",
            ], pw_env)
            deployment_snapshot = snapshot_route(next_base, "/workspace/deployment", [
                "Deployment",
                "Deployment readiness verdict",
                "Backup and restore evidence",
                "Storage backend migration gate",
                "Postgres BYOC gate",
                "SSO and connector policy",
                "browser restore",
            ], pw_env)
            agents_snapshot = snapshot_route(next_base, "/workspace/agents", [
                "Agents",
                "Production security",
                "Adapter readiness",
                "Remote enrollment request",
                "session token omitted",
            ], pw_env)

            transcript.extend([
                proxy_dashboard,
                proxy_agents,
                proxy_security,
                proxy_local,
                proxy_storage,
                proxy_entitlements,
                workspace_snapshot,
                governance_snapshot,
                deployment_snapshot,
                agents_snapshot,
            ])
            assert_no_secret("control tower transcript", transcript)

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "routes": ["/workspace", "/workspace/agents", "/workspace/governance", "/workspace/deployment"],
                "dashboard_metrics": {
                    "agents_total": proxy_dashboard.get("agents_total"),
                    "agents": len(proxy_agents),
                    "runtime_health": len(proxy_dashboard.get("runtime_health") or []),
                    "task_statuses": len(proxy_dashboard.get("task_status_distribution") or []),
                    "cost_leaders": len(proxy_dashboard.get("top_cost_agents") or []),
                },
                "storage_backend": proxy_storage.get("active_backend"),
                "approval_policies_gate": approval_gate.get("status"),
                "secret_leaked": False,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    finally:
        logs = stop_processes(processes)
        run(["bash", "-lc", f"lsof -tiTCP:{next_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["bash", "-lc", f"lsof -tiTCP:{api_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["rm", "-rf", str(NEXT_APP / ".next")], timeout=10)
        restore_next_env()
        if any(proc.returncode not in (0, None, -15) for proc in processes):
            print(json.dumps({"process_logs": logs[-2:]}, ensure_ascii=False, indent=2), file=sys.stderr)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise
