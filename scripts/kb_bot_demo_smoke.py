#!/usr/bin/env python3
"""
Smoke-test the customer knowledge-base bot demo.

This runs the safe local demo and verifies that the product loop creates MIS
ledger evidence, including a customer delivery artifact, without performing an
external knowledge-base upload.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


def http_json(base_url: str, path: str) -> dict | list:
    with urlopen(base_url.rstrip("/") + path, timeout=20) as res:
        raw = res.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def require(condition: bool, message: str, failures: list[str]):
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the Agent Gateway knowledge-base bot customer demo.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--api-key", default=os.environ.get("AGENTOPS_API_KEY", ""))
    args = parser.parse_args()

    cmd = [sys.executable, str(ROOT / "scripts" / "run_kb_bot_demo.py"), "--base-url", args.base_url]
    if args.api_key:
        cmd.extend(["--api-key", args.api_key])
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode or 1
    payload = json.loads(proc.stdout)
    project_id = payload["project_id"]
    results = payload.get("results") or []
    created = payload.get("created_or_updated") or {}
    failures: list[str] = []

    for table in ["tasks", "runs", "tool_calls", "approvals", "memories", "evaluations", "audit_logs", "runtime_events", "artifacts"]:
        require(created.get(table, 0) > 0, f"{table} did not increase", failures)

    require(len(results) == 6, "expected six customer-demo tasks", failures)
    approval_ids = [item.get("approval_id") for item in results if item.get("approval_id")]
    prepared_action_ids = [item.get("prepared_action_id") for item in results if item.get("prepared_action_id")]
    artifact_ids = [item.get("artifact_id") for item in results if item.get("artifact_id")]
    require(bool(approval_ids), "expected pending approval for external knowledge-base upload", failures)
    require(bool(prepared_action_ids), "expected prepared action for external knowledge-base upload", failures)
    require(bool(artifact_ids), "expected customer delivery artifact", failures)
    require(payload.get("safe_defaults", {}).get("external_upload_performed") is False, "external upload should remain false", failures)
    require(payload.get("safe_defaults", {}).get("credentials_stored") is False, "credentials should not be stored", failures)
    require(payload.get("safe_defaults", {}).get("raw_documents_stored") is False, "raw documents should not be stored", failures)

    if approval_ids:
        approvals = http_json(args.base_url, "/api/approvals")
        matching = [item for item in approvals if item.get("approval_id") in approval_ids]
        require(any(item.get("decision") == "pending" for item in matching), "external upload approval should be pending", failures)

    for action_id in prepared_action_ids:
        prepared = http_json(args.base_url, f"/api/agent-gateway/prepared-actions/{action_id}")
        prepared_action = prepared.get("prepared_action") or {}
        require(prepared_action.get("status") == "prepared", f"prepared action should be prepared and unconsumed: {prepared}", failures)
        require((prepared.get("hash_verification") or {}).get("match") is True, f"prepared action hash mismatch: {prepared}", failures)
        require(bool(prepared_action.get("action_hash")), f"prepared action hash missing: {prepared}", failures)
        require(prepared_action.get("consumed_at") is None, f"prepared action should not be consumed by demo: {prepared}", failures)

    if artifact_ids:
        artifacts = http_json(args.base_url, "/api/artifacts")
        matching = [item for item in artifacts if item.get("artifact_id") in artifact_ids]
        require(any("客户交付摘要" in item.get("title", "") for item in matching), "delivery artifact title not found", failures)
        require(all("AGENTOPS_API_KEY" not in json.dumps(item, ensure_ascii=False) for item in matching), "artifact appears to contain secret-like env key text", failures)

    output = {
        "ok": not failures,
        "project_id": project_id,
        "created_or_updated": created,
        "approval_ids": approval_ids,
        "prepared_action_ids": prepared_action_ids,
        "artifact_ids": artifact_ids,
        "open_pages": payload.get("open_pages"),
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
