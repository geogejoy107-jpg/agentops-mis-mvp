#!/usr/bin/env python3
"""Verify AgentOps CLI explains stale base-url sources on connection failure."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-cli-connection-hint-") as tmp:
        config_path = Path(tmp) / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "base_url": "http://127.0.0.1:18787",
                    "workspace_id": "local-demo",
                    "agent_id": "agt_connection_hint_smoke",
                    "api_key": "fake_token_should_not_print",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(config_path)
        env.pop("AGENTOPS_BASE_URL", None)
        proc = subprocess.run(
            [sys.executable, "-m", "agentops_mis_cli.agentops", "status"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        combined = f"{proc.stdout}\n{proc.stderr}"
        require(proc.returncode == 1, f"status should fail against stale base URL: rc={proc.returncode} {combined}", failures)
        require("Cannot reach http://127.0.0.1:18787/api/agent-gateway/status" in combined, f"missing unreachable URL: {combined}", failures)
        require("base_url_source=config" in combined, f"missing base_url source hint: {combined}", failures)
        require(f"config_path={config_path}" in combined, f"missing config path hint: {combined}", failures)
        require("local_demo_default=http://127.0.0.1:8787" in combined, f"missing local demo default hint: {combined}", failures)
        require("agentops login --base-url http://127.0.0.1:8787" in combined, f"missing saved-config repair hint: {combined}", failures)
        require("fake_token_should_not_print" not in combined, "connection hint leaked raw token", failures)

    print(
        json.dumps(
            {
                "ok": not failures,
                "operation": "agentops_cli_connection_hint_smoke",
                "checked": [
                    "stale config base_url",
                    "base_url_source hint",
                    "local demo default hint",
                    "saved config repair hint",
                    "token omission",
                ],
                "failures": failures,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
