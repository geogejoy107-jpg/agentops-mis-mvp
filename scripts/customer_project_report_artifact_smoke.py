#!/usr/bin/env python3
"""Verify customer project reports can be persisted as safe ledger artifacts."""

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
    parser = argparse.ArgumentParser(description="Verify customer project report artifact persistence.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    failures: list[str] = []

    status, project = http_json("POST", args.base_url, "/api/workflows/customer-task-templates/run", {
        "template_id": "tpl_customer_kb_qa_bot",
    })
    require(status == 201 and project.get("ok") is True, f"template project failed: {status} {project}", failures)
    project_id = project.get("project_id")
    require(bool(project_id), f"missing project_id: {project}", failures)

    artifact_path = f"/api/workflows/customer-projects/{project_id}/report-artifact"
    status, artifact_result = http_json("POST", args.base_url, artifact_path, {})
    artifact = artifact_result.get("artifact") or {}
    artifact_id = artifact.get("artifact_id")
    content_hash = artifact_result.get("content_hash")
    require(status == 201, f"report artifact create failed: {status} {artifact_result}", failures)
    require(artifact.get("artifact_type") == "customer_project_report", f"wrong artifact type: {artifact}", failures)
    require(str(project_id) in (artifact.get("title") or ""), f"artifact title missing project id: {artifact}", failures)
    require((artifact.get("uri") or "").endswith(f"/{project_id}/report"), f"artifact uri mismatch: {artifact}", failures)
    require(bool(content_hash), f"missing content hash: {artifact_result}", failures)
    require(artifact_result.get("raw_report_omitted") is True, f"raw report flag missing: {artifact_result}", failures)
    require((artifact_result.get("safe_defaults") or {}).get("raw_documents_stored") is False, f"unsafe defaults: {artifact_result}", failures)

    status, report = http_json("GET", args.base_url, f"/api/workflows/customer-projects/{project_id}/report")
    require(status == 200, f"report fetch failed after artifact: {status} {report}", failures)
    require(report.get("artifact_id") == project.get("artifact_id"), f"delivery artifact was replaced by report artifact: {report}", failures)
    require(report.get("report_artifact_id") == artifact_id, f"report artifact id missing from report: {report}", failures)
    require((report.get("counts") or {}).get("artifacts", 0) >= 2, f"report artifact not counted: {report}", failures)

    status, artifacts = http_json("GET", args.base_url, "/api/artifacts")
    require(status == 200, f"artifacts fetch failed: {status} {artifacts}", failures)
    require(any(row.get("artifact_id") == artifact_id for row in artifacts), f"artifact not listed: {artifact_id}", failures)

    status, audit_rows = http_json("GET", args.base_url, "/api/audit")
    require(status == 200, f"audit fetch failed: {status} {audit_rows}", failures)
    require(any(row.get("action") == "workflow.customer_project.report_artifact" and row.get("entity_id") == artifact_id for row in audit_rows), f"audit missing report artifact action: {artifact_id}", failures)

    serialized = json.dumps({"artifact_result": artifact_result, "report": report}, ensure_ascii=False)
    require("agtok_" not in serialized and "sk-" not in serialized and "ntn_" not in serialized, "report artifact leaked token-like material", failures)

    output = {
        "ok": not failures,
        "project_id": project_id,
        "delivery_artifact_id": project.get("artifact_id"),
        "report_artifact_id": artifact_id,
        "content_hash": content_hash,
        "report_url": artifact_result.get("report_url"),
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
