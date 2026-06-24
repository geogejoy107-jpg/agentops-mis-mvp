#!/usr/bin/env python3
"""Verify CLI live-product-readiness proof is product-facing and read-only."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from live_acceptance_readiness_smoke import add_attempt
from operator_runtime_doctor_smoke import CLI, ROOT, free_port, leaked_secret, load_json, require, wait_ready


LEDGER_TABLES = [
    "tasks",
    "runs",
    "tool_calls",
    "evaluations",
    "runtime_events",
    "audit_logs",
    "artifacts",
    "memories",
    "approvals",
    "plan_evidence_manifests",
]


def ledger_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in LEDGER_TABLES}
    finally:
        conn.close()


def seed_live_acceptance(db_path: Path, workspace_id: str) -> None:
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        add_attempt(
            conn,
            workspace_id=workspace_id,
            adapter="hermes",
            suffix="cli_product_ready",
            hours_delta=-0.1,
            run_status="completed",
            tool_status="completed",
            eval_pass=True,
            manifest_status="verified",
        )
        add_attempt(
            conn,
            workspace_id=workspace_id,
            adapter="openclaw",
            suffix="cli_product_ready",
            hours_delta=-0.1,
            run_status="completed",
            tool_status="completed",
            eval_pass=True,
            manifest_status="verified",
        )
        conn.commit()
    finally:
        conn.close()


def run_cli(base_url: str, env: dict[str, str], *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "--base-url", base_url, "operator", "live-product-readiness", *extra],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-live-product-readiness-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env["AGENTOPS_BASE_URL"] = base_url
        env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
        env.pop("AGENTOPS_API_KEY", None)
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_ready(base_url, proc)
            before_empty = ledger_counts(db_path)
            empty_proc = run_cli(base_url, env, "--require-adapter", "hermes", "--require-adapter", "openclaw")
            outputs.extend([empty_proc.stdout, empty_proc.stderr])
            empty_payload = load_json(empty_proc.stdout)
            require(empty_proc.returncode == 1, f"empty readiness should exit 1: {empty_proc.stdout} {empty_proc.stderr}", failures)
            require(empty_payload.get("product_readiness_proof") is False, f"empty proof should be false: {empty_payload}", failures)
            require(empty_payload.get("operation") == "operator_live_product_readiness", f"empty operation mismatch: {empty_payload}", failures)
            require((empty_payload.get("safety") or {}).get("read_only") is True, f"empty safety missing: {empty_payload}", failures)
            require(ledger_counts(db_path) == before_empty, "empty live-product-readiness mutated ledger tables", failures)

            seed_live_acceptance(db_path, "local-demo")
            before_ready = ledger_counts(db_path)
            ready_proc = run_cli(base_url, env, "--freshness-hours", "72", "--limit", "4")
            outputs.extend([ready_proc.stdout, ready_proc.stderr])
            ready_payload = load_json(ready_proc.stdout)
            require(ready_proc.returncode == 0, f"ready proof should exit 0: {ready_proc.stdout} {ready_proc.stderr}", failures)
            require(ready_payload.get("product_readiness_proof") is True, f"ready proof should be true: {ready_payload}", failures)
            require(ready_payload.get("ok") is True, f"ready ok should be true: {ready_payload}", failures)
            require(ready_payload.get("evidence_class") == "manual_live_ledger_readback", f"ready evidence class mismatch: {ready_payload}", failures)
            adapters = {item.get("adapter"): item for item in ready_payload.get("adapters") or []}
            for adapter in ["hermes", "openclaw"]:
                item = adapters.get(adapter) or {}
                require(item.get("status") == "fresh", f"{adapter} not fresh in ready payload: {item}", failures)
                require(bool(item.get("run_id")), f"{adapter} missing run id: {item}", failures)
                require(bool(item.get("artifact_id")), f"{adapter} missing artifact id: {item}", failures)
                evidence = item.get("evidence") or {}
                for key in ["completed_adapter_tool_calls", "passing_evaluations", "runtime_events", "audit_logs", "customer_worker_artifacts", "memories", "approvals", "verified_plan_evidence_manifests"]:
                    require(int(evidence.get(key) or 0) >= 1, f"{adapter} missing {key}: {evidence}", failures)
            safety = ready_payload.get("safety") or {}
            require(safety.get("read_only") is True, f"ready safety read_only missing: {ready_payload}", failures)
            require(safety.get("live_execution_performed") is False, f"ready proof executed runtime: {ready_payload}", failures)
            require(safety.get("token_omitted") is True, f"ready proof token omission missing: {ready_payload}", failures)
            require(ledger_counts(db_path) == before_ready, "ready live-product-readiness mutated ledger tables", failures)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    combined = "\n".join(outputs)
    require(not leaked_secret(combined), "live-product-readiness output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "operator_live_product_readiness_smoke",
        "failures": failures,
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
    }, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
