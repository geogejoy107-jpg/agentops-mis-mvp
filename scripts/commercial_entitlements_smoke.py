#!/usr/bin/env python3
"""Smoke-test read-only commercial entitlement status API and CLI."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_MARKERS = ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_", "AGENTOPS_API_KEY="]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in SECRET_MARKERS)


def http_json(base_url: str) -> tuple[int, dict]:
    req = urllib.request.Request(base_url.rstrip("/") + "/api/commercial/entitlements", headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"error": exc.reason}
        return exc.code, body


def run_cli(base_url: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "--base-url", base_url, "commercial", "entitlements"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def validate(payload: dict, label: str) -> None:
    require(payload.get("provider") == "agentops-commercial", f"{label} wrong provider: {payload}")
    require(payload.get("operation") == "entitlement_status", f"{label} wrong operation: {payload}")
    require(payload.get("status") == "ready", f"{label} bad status: {payload.get('status')}")
    require(payload.get("edition") == "free_local", f"{label} should default to free_local: {payload}")
    require(payload.get("token_omitted") is True, f"{label} token omission proof missing")
    require(payload.get("live_execution_performed") is False, f"{label} must not execute live work")
    capabilities = payload.get("capabilities") or {}
    require(capabilities.get("sqlite_ledger") is True, f"{label} sqlite ledger should be enabled")
    require(capabilities.get("postgres_adapter") is False, f"{label} postgres adapter should be gated")
    require(capabilities.get("sso_hooks") is False, f"{label} SSO should be gated")
    gates = payload.get("gates") or []
    gate_caps = {gate.get("capability"): gate for gate in gates if isinstance(gate, dict)}
    for capability in ["multi_project", "rbac", "postgres_adapter", "custom_connector_sdk"]:
        require(capability in gate_caps, f"{label} missing gate for {capability}")
        require(gate_caps[capability].get("enforcement") == "read_only_preview", f"{label} unexpected enforcement for {capability}")
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety.read_only missing")
    require(safety.get("billing_call_performed") is False, f"{label} should not call billing")
    require("billing integration" in (payload.get("contract") or ""), f"{label} contract should mention billing boundary")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify commercial entitlement status API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    outputs: list[str] = []
    try:
        status, payload = http_json(args.base_url)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        outputs.append(raw)
        require(status == 200, f"entitlement API failed: {status} {payload}")
        validate(payload, "api")

        with tempfile.TemporaryDirectory(prefix="agentops-commercial-entitlements-") as tmp:
            env = os.environ.copy()
            env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
            env.pop("AGENTOPS_API_KEY", None)
            env.pop("AGENTOPS_EDITION", None)
            proc = run_cli(args.base_url, env)
            outputs.extend([proc.stdout, proc.stderr])
            require(proc.returncode == 0, f"entitlement CLI failed: {proc.stderr or proc.stdout}")
            cli_payload = json.loads(proc.stdout)
            validate(cli_payload, "cli")

        require(not leaked_secret("\n".join(outputs)), "entitlements leaked token-like material")
        print(json.dumps({
            "ok": True,
            "edition": payload.get("edition"),
            "gate_count": len(payload.get("gates") or []),
            "postgres_enabled": payload.get("capabilities", {}).get("postgres_adapter"),
            "billing_call_performed": payload.get("safety", {}).get("billing_call_performed"),
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
