#!/usr/bin/env python3
"""Smoke-test the canonical v1.5 demo readiness aggregate."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_MARKERS = ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_", "AGENTOPS_API_KEY="]
REQUIRED_SHOTS = {
    "local_readiness",
    "security_boundary",
    "worker_fleet",
    "commander_inbox",
    "customer_task_loop",
    "run_ledger_evidence",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in SECRET_MARKERS)


def http_json(base_url: str) -> tuple[int, dict]:
    req = urllib.request.Request(base_url.rstrip("/") + "/api/demo/readiness", headers={"Accept": "application/json"}, method="GET")
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
        [str(CLI), "--base-url", base_url, "demo", "readiness"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def validate(payload: dict, label: str) -> None:
    require(payload.get("provider") == "agentops-demo", f"{label} wrong provider: {payload}")
    require(payload.get("operation") == "v1_5_demo_readiness", f"{label} wrong operation: {payload}")
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"{label} bad status: {payload.get('status')}")
    require(payload.get("token_omitted") is True, f"{label} token omission proof missing")
    require(payload.get("live_execution_performed") is False, f"{label} must not execute live work")
    safety = payload.get("safety") or {}
    for key in ["read_only", "token_omitted", "raw_prompt_omitted"]:
        require(safety.get(key) is True, f"{label} safety {key} missing")
    for key in ["ledger_mutated", "live_execution_performed"]:
        require(safety.get(key) is False, f"{label} safety {key} must be false")
    shots = payload.get("shots") or []
    shot_ids = {shot.get("id") for shot in shots if isinstance(shot, dict)}
    require(REQUIRED_SHOTS.issubset(shot_ids), f"{label} missing shots: {sorted(REQUIRED_SHOTS - shot_ids)}")
    for shot in shots:
        require(shot.get("route") or shot.get("command"), f"{label} shot missing route/command: {shot}")
        require(isinstance(shot.get("ok"), bool), f"{label} shot ok must be bool: {shot}")
    summary = payload.get("summary") or {}
    require(summary.get("shot_count") == len(shots), f"{label} shot_count mismatch")
    require(isinstance(payload.get("next_actions"), list) and payload.get("next_actions"), f"{label} next_actions missing")
    require("read-only" in (payload.get("contract") or ""), f"{label} read-only contract missing")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify v1.5 demo readiness aggregate API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    outputs: list[str] = []
    try:
        status, payload = http_json(args.base_url)
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        outputs.append(raw)
        require(status == 200, f"demo readiness API failed: {status} {payload}")
        validate(payload, "api")

        with tempfile.TemporaryDirectory(prefix="agentops-demo-readiness-") as tmp:
            env = os.environ.copy()
            env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
            env.pop("AGENTOPS_API_KEY", None)
            proc = run_cli(args.base_url, env)
            outputs.extend([proc.stdout, proc.stderr])
            require(proc.returncode == 0, f"demo readiness CLI failed: {proc.stderr or proc.stdout}")
            cli_payload = json.loads(proc.stdout)
            validate(cli_payload, "cli")

        require(not leaked_secret("\n".join(outputs)), "demo readiness leaked token-like material")
        print(json.dumps({
            "ok": True,
            "status": payload.get("status"),
            "demo_ready": payload.get("demo_ready"),
            "production_ready": payload.get("production_ready"),
            "shot_count": len(payload.get("shots") or []),
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
