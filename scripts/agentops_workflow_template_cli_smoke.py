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

    combined = "\n".join([listed.stdout, listed.stderr, run_template.stdout, run_template.stderr])
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
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
