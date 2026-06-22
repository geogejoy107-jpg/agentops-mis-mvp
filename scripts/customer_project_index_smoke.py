#!/usr/bin/env python3
"""Verify customer project index is derived from ledger evidence."""

from __future__ import annotations

import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def http_json(method: str, base_url: str, path: str, payload: dict | None = None):
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(req, timeout=180) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify customer project index.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    failures: list[str] = []

    status, project = http_json("POST", args.base_url, "/api/workflows/customer-task-templates/run", {
        "template_id": "tpl_customer_kb_qa_bot",
    })
    require(status == 201 and project.get("ok") is True, f"template project failed: {status} {project}", failures)
    project_id = project.get("project_id")
    artifact_id = project.get("artifact_id")
    require(bool(project_id), f"missing project_id: {project}", failures)

    status, index = http_json("GET", args.base_url, "/api/workflows/customer-projects?limit=50")
    projects = index.get("projects") or []
    row = next((item for item in projects if item.get("project_id") == project_id), None)
    require(status == 200, f"project index fetch failed: {status} {index}", failures)
    require(row is not None, f"created project missing from index: {project_id}", failures)
    if row:
        require(row.get("task_count") == 6, f"task count mismatch: {row}", failures)
        require(row.get("run_count") == 6, f"run count mismatch: {row}", failures)
        require(row.get("completed_runs") == 5, f"completed runs should exclude the prepared external-upload run: {row}", failures)
        require(row.get("pending_approvals", 0) >= 1, f"pending approval missing: {row}", failures)
        require(row.get("delivery_artifact_id") == artifact_id, f"delivery artifact mismatch: {row}", failures)
        require(row.get("report_url") == f"/api/workflows/customer-projects/{project_id}/report", f"report url mismatch: {row}", failures)
        require(row.get("ui_report_url") == f"/workspace/customer-projects/{project_id}/report", f"ui report url mismatch: {row}", failures)
        require(row.get("status") in {"ready", "waiting_approval"}, f"unexpected status: {row}", failures)
        require((row.get("safe_defaults") or {}).get("raw_documents_stored") is False, f"unsafe defaults: {row}", failures)

    serialized = json.dumps(index, ensure_ascii=False)
    require("agtok_" not in serialized and "sk-" not in serialized and "ntn_" not in serialized, "project index leaked token-like material", failures)

    output = {
        "ok": not failures,
        "project_id": project_id,
        "indexed": row is not None,
        "status": row.get("status") if row else None,
        "delivery_artifact_id": row.get("delivery_artifact_id") if row else None,
        "pending_approvals": row.get("pending_approvals") if row else None,
        "total_projects": index.get("total"),
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
