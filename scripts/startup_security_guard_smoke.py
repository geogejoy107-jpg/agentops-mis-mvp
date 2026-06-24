#!/usr/bin/env python3
"""Verify server startup security guard fails closed for unsafe shared bindings."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def ids(payload: dict) -> set[str]:
    return {item.get("id") for item in payload.get("failures") or [] if isinstance(item, dict)}


def main() -> int:
    failures: list[str] = []
    cases = {
        "loopback_local": server.startup_security_assessment("127.0.0.1", {}),
        "non_loopback_no_auth": server.startup_security_assessment("0.0.0.0", {}),
        "non_loopback_opt_in_no_auth": server.startup_security_assessment("0.0.0.0", {"AGENTOPS_ALLOW_NON_LOOPBACK": "true"}),
        "non_loopback_full_auth": server.startup_security_assessment("0.0.0.0", {
            "AGENTOPS_ALLOW_NON_LOOPBACK": "true",
            "AGENTOPS_API_KEY": "local_test_key",
            "AGENTOPS_ADMIN_KEY": "local_admin_key",
        }),
        "production_loopback_no_auth": server.startup_security_assessment("127.0.0.1", {"AGENTOPS_DEPLOYMENT_MODE": "production"}),
        "production_loopback_full_auth": server.startup_security_assessment("127.0.0.1", {
            "AGENTOPS_DEPLOYMENT_MODE": "production",
            "AGENTOPS_API_KEY": "local_test_key",
            "AGENTOPS_ADMIN_KEY": "local_admin_key",
        }),
        "shared_loopback_no_auth": server.startup_security_assessment("localhost", {"AGENTOPS_DEPLOYMENT_MODE": "shared"}),
    }
    require(cases["loopback_local"]["ok"] is True, f"loopback local should be allowed: {cases['loopback_local']}", failures)
    require(cases["non_loopback_no_auth"]["ok"] is False, f"non-loopback without auth should fail: {cases['non_loopback_no_auth']}", failures)
    require({"non_loopback_requires_opt_in", "agent_gateway_auth_required", "admin_auth_required"}.issubset(ids(cases["non_loopback_no_auth"])), f"missing non-loopback failures: {cases['non_loopback_no_auth']}", failures)
    require(cases["non_loopback_opt_in_no_auth"]["ok"] is False, f"non-loopback opt-in without auth should fail: {cases['non_loopback_opt_in_no_auth']}", failures)
    require("non_loopback_requires_opt_in" not in ids(cases["non_loopback_opt_in_no_auth"]), f"opt-in failure should clear: {cases['non_loopback_opt_in_no_auth']}", failures)
    require({"agent_gateway_auth_required", "admin_auth_required"}.issubset(ids(cases["non_loopback_opt_in_no_auth"])), f"missing auth failures: {cases['non_loopback_opt_in_no_auth']}", failures)
    require(cases["non_loopback_full_auth"]["ok"] is True, f"non-loopback full auth should pass: {cases['non_loopback_full_auth']}", failures)
    require(cases["production_loopback_no_auth"]["ok"] is False, f"production without auth should fail: {cases['production_loopback_no_auth']}", failures)
    require({"agent_gateway_auth_required", "admin_auth_required"}.issubset(ids(cases["production_loopback_no_auth"])), f"missing production failures: {cases['production_loopback_no_auth']}", failures)
    require(cases["production_loopback_full_auth"]["ok"] is True, f"production full auth should pass: {cases['production_loopback_full_auth']}", failures)
    require(cases["shared_loopback_no_auth"]["ok"] is False, f"shared without auth should fail: {cases['shared_loopback_no_auth']}", failures)
    serialized = json.dumps(cases, ensure_ascii=False)
    require("local_test_key" not in serialized and "local_admin_key" not in serialized, "startup guard leaked configured key values", failures)
    with tempfile.TemporaryDirectory(prefix="agentops-startup-guard-") as tmp:
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(Path(tmp) / "guard.db")
        for name in ["AGENTOPS_API_KEY", "AGENTOPS_ADMIN_KEY", "AGENTOPS_ALLOW_NON_LOOPBACK", "AGENTOPS_DEPLOYMENT_MODE", "AGENTOPS_REQUIRE_PRODUCTION_SECURITY"]:
            env.pop(name, None)
        non_loopback_proc = subprocess.run(
            [sys.executable, str(ROOT / "server.py"), "--host", "0.0.0.0", "--port", "59991"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        require(non_loopback_proc.returncode == 2, f"non-loopback server start should exit 2: rc={non_loopback_proc.returncode} stderr={non_loopback_proc.stderr[:1000]}", failures)
        require("unsafe_startup_configuration" in non_loopback_proc.stderr, f"non-loopback stderr missing unsafe marker: {non_loopback_proc.stderr[:1000]}", failures)
        production_env = env.copy()
        production_env["AGENTOPS_DEPLOYMENT_MODE"] = "production"
        production_proc = subprocess.run(
            [sys.executable, str(ROOT / "server.py"), "--host", "127.0.0.1", "--port", "59992"],
            cwd=ROOT,
            env=production_env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        require(production_proc.returncode == 2, f"production server start should exit 2: rc={production_proc.returncode} stderr={production_proc.stderr[:1000]}", failures)
        require("unsafe_startup_configuration" in production_proc.stderr, f"production stderr missing unsafe marker: {production_proc.stderr[:1000]}", failures)
        require(not any(marker in (non_loopback_proc.stderr + production_proc.stderr) for marker in ["local_test_key", "local_admin_key", "AGENTOPS_API_KEY="]), "startup failure output leaked secret-like material", failures)
    print(json.dumps({"ok": not failures, "cases": cases, "failures": failures}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
