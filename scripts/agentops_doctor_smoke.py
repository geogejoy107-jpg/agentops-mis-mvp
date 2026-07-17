#!/usr/bin/env python3
"""Smoke-test agentops doctor for local and scoped-token contexts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import argparse
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def run(cmd: list[str], *, env: dict[str, str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test agentops doctor for local and scoped-token contexts.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    agent_id = f"agt_doctor_smoke_{stamp}"
    with tempfile.TemporaryDirectory(prefix="agentops-doctor-") as tmp:
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env["AGENTOPS_BASE_URL"] = args.base_url
        env.pop("AGENTOPS_API_KEY", None)
        env.pop("AGENTOPS_AGENT_ID", None)

        local_doctor = run([str(CLI), "doctor"], env=env)
        local_payload = load_json(local_doctor)
        production_env = env.copy()
        production_env["AGENTOPS_DEPLOYMENT_MODE"] = "production"
        production_env.pop("AGENTOPS_API_KEY", None)
        production_doctor = run([str(CLI), "doctor"], env=production_env)
        production_payload = load_json(production_doctor)

        create = run([
            str(CLI),
            "enrollment",
            "create",
            "--agent-id",
            agent_id,
            "--name",
            "Doctor Smoke Agent",
            "--runtime",
            "mock",
            "--scopes",
            "agents:heartbeat,tasks:read,audit:write",
            "--ttl-days",
            "1",
        ], env=env)
        create_payload = load_json(create)
        token = create_payload.get("token", "")
        token_id = create_payload.get("token_id")

        token_env = env.copy()
        token_env["AGENTOPS_API_KEY"] = token
        token_env["AGENTOPS_AGENT_ID"] = agent_id
        token_doctor = run([str(CLI), "doctor"], env=token_env)
        token_payload = load_json(token_doctor)

        revoke = run([str(CLI), "enrollment", "revoke", "--token-id", str(token_id)], env=env) if token_id else None
        revoke_payload = load_json(revoke) if revoke else {}
        stale_token = "fake_stale_config_token_should_not_print"
        Path(env["AGENTOPS_CONFIG"]).write_text(
            json.dumps(
                {
                    "base_url": args.base_url,
                    "workspace_id": "local-demo",
                    "agent_id": "agt_stale_config_doctor_smoke",
                    "api_key": stale_token,
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        stale_config_doctor = run([str(CLI), "doctor"], env=env)
        stale_config_payload = load_json(stale_config_doctor)
        stale_config_readback = run([str(CLI), "operator", "local-harness-proof", "--limit", "1"], env=env)
        stale_config_readback_payload = load_json(stale_config_readback)

        ok = (
            local_doctor.returncode == 0
            and local_payload.get("ok") is True
            and local_payload.get("auth", {}).get("api_key_source") == "missing"
            and local_payload.get("auth", {}).get("token_omitted") is True
            and production_doctor.returncode == 2
            and production_payload.get("ok") is False
            and (production_payload.get("deployment_safety") or {}).get("ok") is False
            and (production_payload.get("deployment_safety") or {}).get("strict_exit_code") == 2
            and (production_payload.get("deployment_safety") or {}).get("blocks_unsafe_shared_deployment") is True
            and (production_payload.get("deployment_safety") or {}).get("production_requested") is True
            and create.returncode == 0
            and bool(token)
            and token_doctor.returncode == 0
            and token_payload.get("ok") is True
            and token_payload.get("auth", {}).get("api_key_source") == "env"
            and token_payload.get("auth", {}).get("token_omitted") is True
            and token_payload.get("gateway", {}).get("token_omitted") is True
            and token not in token_doctor.stdout
            and (revoke is not None and revoke.returncode == 0)
            and stale_config_doctor.returncode == 0
            and stale_config_payload.get("ok") is True
            and stale_config_payload.get("auth", {}).get("api_key_source") == "config"
            and stale_config_payload.get("stale_config_token_ignored_for_local_loopback") is True
            and any(
                item.get("stale_config_token_ignored_for_local_loopback") is True
                for item in (stale_config_payload.get("checks") or [])
            )
            and stale_config_readback.returncode == 0
            and stale_config_readback_payload.get("operation") == "local_harness_proof_readiness"
            and stale_token not in stale_config_doctor.stdout
            and stale_token not in stale_config_doctor.stderr
            and stale_token not in stale_config_readback.stdout
            and stale_token not in stale_config_readback.stderr
        )
        print(json.dumps({
            "ok": ok,
            "base_url": args.base_url,
            "agent_id": agent_id,
            "token_id": token_id,
            "local_doctor_returncode": local_doctor.returncode,
            "local_auth_source": local_payload.get("auth", {}).get("api_key_source"),
            "production_doctor_returncode": production_doctor.returncode,
            "production_doctor_ok": production_payload.get("ok"),
            "production_deployment_safety": production_payload.get("deployment_safety"),
            "token_doctor_returncode": token_doctor.returncode,
            "token_auth_source": token_payload.get("auth", {}).get("api_key_source"),
            "token_omitted": token_payload.get("auth", {}).get("token_omitted") is True and token_payload.get("gateway", {}).get("token_omitted") is True,
            "token_leaked": bool(token and token in token_doctor.stdout),
            "revoke_returncode": revoke.returncode if revoke else None,
            "revoked": revoke_payload.get("revoked"),
            "stale_config_doctor_returncode": stale_config_doctor.returncode,
            "stale_config_readback_returncode": stale_config_readback.returncode,
            "stale_config_token_ignored": stale_config_payload.get("stale_config_token_ignored_for_local_loopback"),
        }, ensure_ascii=False, indent=2, sort_keys=True))
        if not ok:
            print("local stderr:", local_doctor.stderr[-1200:], file=sys.stderr)
            print("production stderr:", production_doctor.stderr[-1200:], file=sys.stderr)
            print("create stderr:", create.stderr[-1200:], file=sys.stderr)
            print("token stderr:", token_doctor.stderr[-1200:], file=sys.stderr)
            if revoke:
                print("revoke stderr:", revoke.stderr[-1200:], file=sys.stderr)
            print("stale config stderr:", stale_config_doctor.stderr[-1200:], file=sys.stderr)
            print("stale config readback stderr:", stale_config_readback.stderr[-1200:], file=sys.stderr)
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
