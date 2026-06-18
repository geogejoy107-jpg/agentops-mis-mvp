#!/usr/bin/env python3
"""Verify customer project delivery report export is generated from ledger evidence."""

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
    parser = argparse.ArgumentParser(description="Verify customer project report export.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    failures: list[str] = []

    status, project = http_json("POST", args.base_url, "/api/workflows/customer-task-templates/run", {
        "template_id": "tpl_customer_kb_qa_bot",
    })
    require(status == 201 and project.get("ok") is True, f"template project failed: {status} {project}", failures)
    project_id = project.get("project_id")
    report_url = project.get("report_url") or f"/api/workflows/customer-projects/{project_id}/report"
    require(bool(project_id), f"missing project_id: {project}", failures)
    require(bool(report_url), f"missing report_url: {project}", failures)

    status, report = http_json("GET", args.base_url, report_url)
    markdown = report.get("markdown") or ""
    counts = report.get("counts") or {}
    require(status == 200, f"report fetch failed: {status} {report}", failures)
    require(report.get("project_id") == project_id, f"report project mismatch: {report}", failures)
    require(counts.get("tasks") == 6, f"report task count mismatch: {counts}", failures)
    require(counts.get("runs") == 6, f"report run count mismatch: {counts}", failures)
    require(counts.get("pending_approvals", 0) >= 1, f"report missing pending approval: {counts}", failures)
    require(report.get("artifact_id") == project.get("artifact_id"), f"report artifact mismatch: {report}", failures)
    require(str(project_id) in markdown, "markdown missing project id", failures)
    require(str(project.get("artifact_id")) in markdown, "markdown missing artifact id", failures)
    require("External upload performed: false" in markdown, "markdown missing external upload safety boundary", failures)
    require("Raw documents stored in MIS: false" in markdown, "markdown missing raw document safety boundary", failures)
    require("Task Ledger" in markdown, "markdown missing task ledger section", failures)
    serialized = json.dumps(report, ensure_ascii=False)
    require("agtok_" not in serialized and "sk-" not in serialized and "ntn_" not in serialized, "report leaked token-like material", failures)

    output = {
        "ok": not failures,
        "project_id": project_id,
        "report_url": report_url,
        "artifact_id": report.get("artifact_id"),
        "approval_ids": report.get("approval_ids"),
        "counts": counts,
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
