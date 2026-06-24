#!/usr/bin/env python3
"""
Smoke-test the browser-facing KB bot project workflow endpoint.

This verifies that a customer can start the six-step project from the MIS API
without running the demo script manually.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def http_json(method: str, base_url: str, path: str, payload: dict | None = None):
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(req, timeout=180) as res:
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def require(condition: bool, message: str, failures: list[str]):
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify browser-facing KB bot project workflow endpoint.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    result = http_json("POST", args.base_url, "/api/workflows/kb-bot-project", {})
    failures: list[str] = []
    require(result.get("ok") is True, "workflow did not return ok=true", failures)
    require(bool(result.get("project_id")), "missing project_id", failures)
    require(len(result.get("results") or []) == 6, "expected six project steps", failures)
    require(bool(result.get("task_id")), "missing final task_id", failures)
    require(bool(result.get("run_id")), "missing final run_id", failures)
    require(bool(result.get("artifact_id")), "missing delivery artifact", failures)
    require(bool(result.get("approval_ids")), "missing pending approval id", failures)
    safe = result.get("safe_defaults") or {}
    require(safe.get("external_upload_performed") is False, "external upload should remain false", failures)
    require(safe.get("credentials_stored") is False, "credentials should not be stored", failures)
    require(safe.get("raw_documents_stored") is False, "raw documents should not be stored", failures)

    if result.get("task_id"):
        task_detail = http_json("GET", args.base_url, f"/api/tasks/{result['task_id']}")
        require(len(task_detail.get("artifacts") or []) >= 1, "final task detail has no artifact", failures)
    if result.get("approval_ids"):
        approvals = http_json("GET", args.base_url, "/api/approvals")
        matching = [item for item in approvals if item.get("approval_id") in result["approval_ids"]]
        require(any(item.get("decision") == "pending" for item in matching), "approval is not pending", failures)

    output = {
        "ok": not failures,
        "project_id": result.get("project_id"),
        "task_id": result.get("task_id"),
        "run_id": result.get("run_id"),
        "artifact_id": result.get("artifact_id"),
        "approval_ids": result.get("approval_ids"),
        "steps": len(result.get("results") or []),
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
