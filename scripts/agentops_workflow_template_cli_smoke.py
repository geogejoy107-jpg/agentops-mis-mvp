#!/usr/bin/env python3
"""Smoke-test customer task template CLI commands."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def secret_leaked(text: str) -> bool:
    if any(marker in text for marker in ["Authorization:", "Bearer ", "agtok_", "agtsess_", "ntn_"]):
        return True
    return bool(re.search(r"sk-[A-Za-z0-9_-]{20,}", text))


def main() -> int:
    listed = run(["workflow", "templates"])
    listed_payload = load_json(listed)
    templates = listed_payload.get("templates") or []
    template_ids = {item.get("template_id") for item in templates}
    require(listed.returncode == 0, f"template list failed: {listed.stderr or listed.stdout}")
    require("tpl_customer_kb_qa_bot" in template_ids, f"KB bot template missing: {template_ids}")
    require(len(templates) >= 3, f"expected at least three templates, got {len(templates)}")

    run_template = run([
        "workflow",
        "run-template",
        "--template-id",
        "tpl_customer_kb_qa_bot",
    ])
    payload = load_json(run_template)
    safe = payload.get("safe_defaults") or {}
    require(run_template.returncode == 0, f"run-template failed: {run_template.stderr or run_template.stdout}")
    require(payload.get("ok") is True, f"run-template did not return ok=true: {payload}")
    require((payload.get("template") or {}).get("template_id") == "tpl_customer_kb_qa_bot", f"wrong template metadata: {payload}")
    require(len(payload.get("results") or []) == 6, f"expected six KB steps: {payload}")
    require(bool(payload.get("project_id")), f"missing project id: {payload}")
    require(bool(payload.get("artifact_id")), f"missing delivery artifact: {payload}")
    require(bool(payload.get("approval_ids")), f"missing pending approval: {payload}")
    require(bool(payload.get("report_url")), f"missing report url: {payload}")
    require(safe.get("external_upload_performed") is False, f"external upload should remain false: {safe}")
    require(safe.get("credentials_stored") is False, f"credentials should not be stored: {safe}")
    require(safe.get("raw_documents_stored") is False, f"raw documents should not be stored: {safe}")

    worker_template = run([
        "workflow",
        "run-template",
        "--template-id",
        "tpl_customer_ui_review",
        "--adapter",
        "mock",
    ])
    worker_payload = load_json(worker_template)
    worker_evidence = worker_payload.get("evidence") or {}
    require(worker_template.returncode == 0, f"worker template failed: {worker_template.stderr or worker_template.stdout}")
    require(worker_payload.get("provider") == "agentops-worker", f"worker template should use worker provider: {worker_payload}")
    require(worker_payload.get("workflow") == "customer_worker_task", f"worker template should dispatch customer worker task: {worker_payload}")
    require(worker_payload.get("ok") is True, f"worker template did not complete: {worker_payload}")
    require(worker_payload.get("dry_run") is False, f"mock worker template should write real ledger evidence: {worker_payload}")
    require((worker_payload.get("template_execution") or {}).get("mode") == "agent_worker_adapter", f"missing template execution metadata: {worker_payload}")
    require((worker_payload.get("template_execution") or {}).get("adapter") == "mock", f"wrong worker adapter metadata: {worker_payload}")
    require(worker_evidence.get("tool_calls", 0) >= 1, f"worker template missing tool evidence: {worker_evidence}")
    require(worker_evidence.get("evaluations", 0) >= 1, f"worker template missing eval evidence: {worker_evidence}")
    require(worker_evidence.get("audit_logs", 0) >= 1, f"worker template missing audit evidence: {worker_evidence}")
    require(worker_evidence.get("artifacts", 0) >= 1, f"worker template missing artifact evidence: {worker_evidence}")
    require(worker_evidence.get("approvals", 0) >= 1, f"worker template missing approval evidence: {worker_evidence}")

    confirm_gate = run([
        "workflow",
        "run-template",
        "--template-id",
        "tpl_customer_ui_review",
        "--adapter",
        "hermes",
    ])
    confirm_payload = load_json(confirm_gate)
    require(confirm_gate.returncode == 0, f"confirm gate template failed: {confirm_gate.stderr or confirm_gate.stdout}")
    require(confirm_payload.get("provider") == "agentops-worker", f"confirm gate should use worker provider: {confirm_payload}")
    require(confirm_payload.get("dry_run") is True, f"Hermes template without confirm should be dry-run/planned: {confirm_payload}")
    require(confirm_payload.get("reason") == "confirm_run_required_for_live_adapter", f"confirm gate reason missing: {confirm_payload}")
    require((confirm_payload.get("template_execution") or {}).get("adapter") == "hermes", f"confirm gate adapter metadata missing: {confirm_payload}")

    combined = "\n".join([
        listed.stdout,
        listed.stderr,
        run_template.stdout,
        run_template.stderr,
        worker_template.stdout,
        worker_template.stderr,
        confirm_gate.stdout,
        confirm_gate.stderr,
    ])
    require(not secret_leaked(combined), "workflow template CLI output leaked token-like material")
    print(json.dumps({
        "ok": True,
        "template_count": len(templates),
        "project_id": payload.get("project_id"),
        "task_id": payload.get("task_id"),
        "run_id": payload.get("run_id"),
        "artifact_id": payload.get("artifact_id"),
        "approval_ids": payload.get("approval_ids"),
        "report_url": payload.get("report_url"),
        "steps": len(payload.get("results") or []),
        "worker_template_run_id": worker_payload.get("run_id"),
        "worker_template_artifact_id": worker_payload.get("artifact_id"),
        "worker_template_evidence": worker_evidence,
        "confirm_gate_task_id": confirm_payload.get("task_id"),
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
