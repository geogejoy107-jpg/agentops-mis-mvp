#!/usr/bin/env python3
"""Smoke-test the read-only worker fleet lane view."""
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


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in SECRET_MARKERS)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def http_json(base_url: str, path: str) -> tuple[int, dict]:
    req = urllib.request.Request(base_url.rstrip("/") + path, headers={"Accept": "application/json"}, method="GET")
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
        [str(CLI), "--base-url", base_url, "worker", "fleet"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def validate(payload: dict, label: str) -> None:
    require(payload.get("provider") == "agentops-worker", f"{label} wrong provider: {payload}")
    require(payload.get("operation") == "fleet_view", f"{label} wrong operation: {payload}")
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"{label} bad status: {payload.get('status')}")
    require(payload.get("token_omitted") is True, f"{label} token omission proof missing")
    require(payload.get("live_execution_performed") is False, f"{label} must not execute live work")
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety.read_only missing")
    require(safety.get("token_omitted") is True, f"{label} safety.token_omitted missing")
    require(safety.get("session_id_omitted") is True, f"{label} safety.session_id_omitted missing")
    require(safety.get("raw_prompt_omitted") is True, f"{label} safety.raw_prompt_omitted missing")
    summary = payload.get("summary") or {}
    lanes = payload.get("lanes")
    require(isinstance(lanes, list), f"{label} lanes missing")
    require(summary.get("lane_count") == len(lanes), f"{label} lane count mismatch")
    require(isinstance(summary.get("lane_counts"), dict), f"{label} lane_counts missing")
    require(isinstance(summary.get("health_counts"), dict), f"{label} health_counts missing")
    require(isinstance(payload.get("next_actions"), list) and payload.get("next_actions"), f"{label} next_actions missing")
    require("CLI/API" in (payload.get("contract") or ""), f"{label} contract missing CLI/API boundary")
    for lane in lanes:
        require(lane.get("lane_id") and lane.get("lane_type"), f"{label} bad lane: {lane}")
        require(lane.get("health") in {"pass", "warn", "fail", "info"}, f"{label} bad lane health: {lane}")
        require(lane.get("token_omitted") is True, f"{label} lane token proof missing: {lane}")
        require(lane.get("session_id_omitted") is True, f"{label} lane session proof missing: {lane}")
        require("token_id" not in lane or lane.get("token_id_omitted") is True, f"{label} raw token id exposed: {lane}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify worker fleet lane view API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    outputs: list[str] = []
    try:
        status, payload = http_json(args.base_url, "/api/workers/fleet")
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        outputs.append(raw)
        require(status == 200, f"worker fleet API failed: {status} {payload}")
        validate(payload, "api")

        with tempfile.TemporaryDirectory(prefix="agentops-worker-fleet-") as tmp:
            env = os.environ.copy()
            env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
            env.pop("AGENTOPS_API_KEY", None)
            proc = run_cli(args.base_url, env)
            outputs.extend([proc.stdout, proc.stderr])
            require(proc.returncode == 0, f"agentops worker fleet failed: {proc.stderr or proc.stdout}")
            cli_payload = json.loads(proc.stdout)
            validate(cli_payload, "cli")

        combined = "\n".join(outputs)
        require(not leaked_secret(combined), "worker fleet output leaked token-like material")
        print(json.dumps({
            "ok": True,
            "status": payload.get("status"),
            "lane_count": len(payload.get("lanes") or []),
            "lane_counts": (payload.get("summary") or {}).get("lane_counts"),
            "health_counts": (payload.get("summary") or {}).get("health_counts"),
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
