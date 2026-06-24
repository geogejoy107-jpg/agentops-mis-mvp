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
AI_EMPLOYEES = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "AIEmployees.tsx"
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"
SECRET_MARKERS = ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_", "AGENTOPS_API_KEY="]
REQUIRED_SHOTS = {
    "local_readiness",
    "security_boundary",
    "worker_fleet",
    "commander_inbox",
    "customer_task_loop",
    "live_acceptance_freshness",
    "run_ledger_evidence",
}
REQUIRED_PRODUCT_EVIDENCE_PHASES = {
    "readiness",
    "non_live_acceptance",
    "current_code_product_evidence",
    "real_runtime_acceptance",
    "live_readback",
    "remote_worker_fallback",
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
    require("live_acceptance_fresh_adapters" in summary, f"{label} live acceptance summary missing: {summary}")
    live = payload.get("live_acceptance_readiness") or {}
    require(live.get("operation") == "live_acceptance_readiness", f"{label} live acceptance readiness missing: {live}")
    require((live.get("safety") or {}).get("read_only") is True, f"{label} live acceptance read-only proof missing: {live}")
    packet = payload.get("product_evidence_packet") or {}
    require(packet.get("operation") == "product_evidence_packet", f"{label} product evidence packet missing: {packet}")
    require("read-only" in (packet.get("contract") or ""), f"{label} product evidence read-only contract missing")
    packet_safety = packet.get("safety") or {}
    for key in ["read_only", "token_omitted", "raw_prompt_omitted", "requires_confirm_live", "requires_isolated_db_for_live"]:
        require(packet_safety.get(key) is True, f"{label} product evidence safety {key} missing")
    for key in ["ledger_mutated", "live_execution_performed"]:
        require(packet_safety.get(key) is False, f"{label} product evidence safety {key} must be false")
    phases = packet.get("phases") or []
    phase_ids = {phase.get("id") for phase in phases if isinstance(phase, dict)}
    require(REQUIRED_PRODUCT_EVIDENCE_PHASES.issubset(phase_ids), f"{label} missing product evidence phases: {sorted(REQUIRED_PRODUCT_EVIDENCE_PHASES - phase_ids)}")
    for phase in phases:
        require(phase.get("command"), f"{label} product evidence phase missing command: {phase}")
        require(isinstance(phase.get("requires_confirm_live"), bool), f"{label} product evidence phase confirm-live flag must be bool: {phase}")
        require(isinstance(phase.get("requires_isolated_db"), bool), f"{label} product evidence phase isolated-db flag must be bool: {phase}")
    packet_summary = packet.get("summary") or {}
    require(packet_summary.get("phase_count") == len(phases), f"{label} product evidence phase_count mismatch")
    current_code_phase = next((phase for phase in phases if phase.get("id") == "current_code_product_evidence"), {})
    require(current_code_phase.get("requires_confirm_live") is True, f"{label} current-code phase must require confirm-live")
    require(current_code_phase.get("requires_isolated_db") is True, f"{label} current-code phase must require isolated db")
    require("v1_5_current_code_product_evidence.py" in (current_code_phase.get("command") or ""), f"{label} current-code command missing")
    require(isinstance(payload.get("next_actions"), list) and payload.get("next_actions"), f"{label} next_actions missing")
    require("read-only" in (payload.get("contract") or ""), f"{label} read-only contract missing")


def validate_ui_contract() -> None:
    ai_text = AI_EMPLOYEES.read_text(encoding="utf-8")
    api_text = LIVE_API.read_text(encoding="utf-8")
    required_ai_markers = [
        "productEvidencePacket",
        "product_evidence_packet",
        "copyIntakeCommand(phase.command)",
        "requires_confirm_live",
        "requires_isolated_db",
    ]
    required_api_markers = [
        "DemoProductEvidencePacket",
        "product_evidence_packet",
        "requires_confirm_live",
        "requires_isolated_db_for_live",
        "manual_live_phase_count",
    ]
    for marker in required_ai_markers:
        require(marker in ai_text, f"AIEmployees missing product evidence UI marker: {marker}")
    for marker in required_api_markers:
        require(marker in api_text, f"liveApi missing product evidence parser marker: {marker}")


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

        validate_ui_contract()
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
