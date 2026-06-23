#!/usr/bin/env python3
"""Collect repeatable v1.5 current-code product evidence.

This script is a thin orchestrator around existing acceptance tools. It assumes
an AgentOps MIS server is already running and writes only to that server's
configured ledger. Use an isolated AGENTOPS_DB_PATH server for live dogfood.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def run_json(command: list[str], env: dict[str, str], timeout: int) -> tuple[int, dict[str, Any], str]:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    raw = proc.stdout.strip() or proc.stderr.strip()
    try:
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {"raw": raw[:2000]}
    return proc.returncode, payload, raw


def http_get_json(base_url: str, path: str, timeout: int = 30) -> dict[str, Any]:
    req = urllib.request.Request(base_url.rstrip("/") + path, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def compact_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = payload.get("evidence") or {}
    gates = payload.get("gates") or []
    return {
        "status": payload.get("status"),
        "local_demo_ready": payload.get("local_demo_ready"),
        "running_instance_current": evidence.get("running_instance_current"),
        "knowledge_documents": evidence.get("knowledge_documents"),
        "knowledge_chunks": evidence.get("knowledge_chunks"),
        "commander_synthesis_artifacts": evidence.get("commander_synthesis_artifacts"),
        "commander_synthesis_promoted_deliveries": evidence.get("commander_synthesis_promoted_deliveries"),
        "live_acceptance_fresh_adapters": evidence.get("live_acceptance_fresh_adapters"),
        "closed_loop_runs": evidence.get("closed_loop_runs"),
        "ready_gates": [gate.get("id") for gate in gates if gate.get("ok") is True],
        "attention_gates": [gate.get("id") for gate in gates if gate.get("ok") is not True],
        "token_omitted": payload.get("token_omitted") is True,
    }


def compact_step_payload(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if name == "knowledge_index":
        return {
            "operation": payload.get("operation"),
            "indexed": payload.get("indexed"),
            "chunks_indexed": payload.get("chunks_indexed"),
            "fts_available": payload.get("fts_available"),
            "chunk_fts_available": payload.get("chunk_fts_available"),
            "token_omitted": payload.get("token_omitted") is True,
        }
    if name == "commander_synthesis":
        return {
            "ok": payload.get("ok"),
            "plan_id": payload.get("plan_id"),
            "artifact_id": payload.get("artifact_id"),
            "delivery_artifact_id": payload.get("delivery_artifact_id"),
            "approval_id": payload.get("approval_id"),
            "evidence": payload.get("evidence"),
            "promotion_evidence": payload.get("promotion_evidence"),
            "secret_leaked": payload.get("secret_leaked") is True,
        }
    if name == "real_hermes_openclaw_acceptance":
        return {
            "ok": payload.get("ok"),
            "operation": payload.get("operation"),
            "results": [
                {
                    "adapter": item.get("adapter"),
                    "ok": item.get("ok"),
                    "task_id": item.get("task_id"),
                    "run_id": item.get("run_id"),
                    "artifact_id": item.get("artifact_id"),
                    "approval_id": item.get("approval_id"),
                    "plan_evidence_manifest_id": item.get("plan_evidence_manifest_id"),
                    "evidence": item.get("evidence"),
                }
                for item in payload.get("results") or []
            ],
            "token_omitted": payload.get("token_omitted") is True,
        }
    if name == "live_product_readiness_readback":
        return {
            "ok": payload.get("ok"),
            "product_readiness_proof": payload.get("product_readiness_proof"),
            "live_acceptance_status": payload.get("live_acceptance_status"),
            "local_readiness_status": payload.get("local_readiness_status"),
            "adapters": [
                {
                    "adapter": item.get("adapter"),
                    "status": item.get("status"),
                    "run_id": item.get("run_id"),
                    "task_id": item.get("task_id"),
                    "artifact_id": item.get("artifact_id"),
                    "plan_evidence_manifest_id": item.get("plan_evidence_manifest_id"),
                    "evidence": item.get("evidence"),
                }
                for item in payload.get("adapters") or []
            ],
        }
    if name == "non_live_local_acceptance":
        return {
            "ok": payload.get("ok"),
            "check_count": payload.get("check_count"),
            "failure_count": payload.get("failure_count"),
            "ledger_stability": payload.get("ledger_stability"),
            "live_execution_performed": payload.get("live_execution_performed"),
            "mutating_actions_performed": payload.get("mutating_actions_performed"),
            "product_readiness_proof": payload.get("product_readiness_proof"),
        }
    return {
        "ok": payload.get("ok"),
        "operation": payload.get("operation"),
        "status": payload.get("status"),
        "token_omitted": payload.get("token_omitted") is True if "token_omitted" in payload else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect v1.5 current-code product evidence from a running MIS server.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument(
        "--db-path",
        default=os.environ.get("AGENTOPS_DB_PATH") or str(ROOT / "agentops_mis.db"),
        help="SQLite DB used by server-backed smokes that verify ledger rows directly.",
    )
    parser.add_argument("--confirm-live", action="store_true", help="Run real local Hermes/OpenClaw acceptance.")
    parser.add_argument("--skip-knowledge-index", action="store_true")
    parser.add_argument("--skip-commander-synthesis", action="store_true")
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--hermes-timeout", type=int, default=600)
    parser.add_argument("--hermes-max-tokens", type=int, default=512)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_DB_PATH"] = args.db_path

    steps: list[dict[str, Any]] = []
    failures: list[str] = []

    def record_step(name: str, command: list[str], timeout: int) -> dict[str, Any]:
        rc, payload, raw = run_json(command, env, timeout)
        ok = rc == 0 and payload.get("ok", True) is not False
        item = {
            "name": name,
            "ok": ok,
            "returncode": rc,
            "command": " ".join(command),
            "summary": compact_step_payload(name, payload),
        }
        if not ok:
            item["raw_tail"] = raw[-2000:]
            failures.append(f"{name} failed")
        steps.append(item)
        return payload

    try:
        before = compact_readiness(http_get_json(base_url, "/api/local/readiness"))
        if (
            before.get("running_instance_current") is True
            and args.db_path == str(ROOT / "agentops_mis.db")
            and base_url != "http://127.0.0.1:8787"
        ):
            failures.append("non_default_base_url_requires_explicit_db_path")
        if not args.skip_knowledge_index:
            record_step("knowledge_index", [str(CLI), "knowledge", "index", "--rebuild"], args.timeout)
        if not args.skip_commander_synthesis:
            record_step("commander_synthesis", ["python3", "scripts/commander_work_package_synthesis_smoke.py"], args.timeout)
        if not args.skip_live:
            if args.confirm_live:
                record_step(
                    "real_hermes_openclaw_acceptance",
                    [
                        "python3",
                        "scripts/customer_worker_real_runtime_acceptance.py",
                        "--base-url",
                        base_url,
                        "--confirm-live",
                        "--adapter",
                        "hermes",
                        "--adapter",
                        "openclaw",
                        "--request-timeout",
                        str(args.timeout),
                        "--hermes-timeout",
                        str(args.hermes_timeout),
                        "--hermes-max-tokens",
                        str(args.hermes_max_tokens),
                    ],
                    args.timeout + 60,
                )
                record_step(
                    "live_product_readiness_readback",
                    [
                        "python3",
                        "scripts/v1_5_live_product_readiness_smoke.py",
                        "--base-url",
                        base_url,
                        "--require-adapter",
                        "hermes",
                        "--require-adapter",
                        "openclaw",
                    ],
                    120,
                )
            else:
                steps.append({
                    "name": "real_hermes_openclaw_acceptance",
                    "ok": True,
                    "skipped": True,
                    "reason": "confirm_live_required",
                })
        record_step("non_live_local_acceptance", ["python3", "scripts/v1_5_local_product_acceptance.py", "--base-url", base_url], 180)
        after = compact_readiness(http_get_json(base_url, "/api/local/readiness"))
    except Exception as exc:
        before = locals().get("before", {})
        after = {}
        failures.append(str(exc))

    output = {
        "operation": "v1_5_current_code_product_evidence",
        "ok": not failures and all(step.get("ok") for step in steps),
        "base_url": base_url,
        "evidence_class": "current_code_local_product_evidence",
        "live_execution_requested": bool(args.confirm_live and not args.skip_live),
        "before": before,
        "after": after,
        "steps": steps,
        "failures": failures,
        "safety": {
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
            "repo_artifacts_written": False,
            "requires_isolated_db_for_live": True,
        },
        "token_omitted": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
