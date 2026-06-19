#!/usr/bin/env python3
"""Run a hard-coded local Hermes/OpenClaw dogfood task through AgentOps MIS."""
from __future__ import annotations

import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DOGFOOD_TITLE = "用真实 Hermes / OpenClaw 优化 AgentOps MIS 客户工作台"
DOGFOOD_DESCRIPTION = (
    "请以一人公司客户视角审视 AgentOps MIS 当前 Pixel Office / AI Employees / Run Ledger 工作流。"
    "目标是找出客户创建任务、AI 团队执行、审批、评估、审计、交付报告这一闭环里最影响真实使用的 3-5 个问题，"
    "并给出下一步产品改进建议。不要请求外部联网，不要读取私聊或凭证，只基于任务说明和 MIS 运行上下文输出。"
)
DOGFOOD_ACCEPTANCE = (
    "必须给出可执行的产品建议；必须说明哪些由 agent worker 解决，哪些由 MIS UI/权限/审计解决；"
    "必须写入 runs、tool_calls、evaluations、audit_logs 和 customer_worker_result artifact。"
)


def http_json(method: str, base_url: str, path: str, payload: dict | None = None):
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(req, timeout=360) as res:
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


def run_adapter(base_url: str, adapter: str, failures: list[str]) -> dict:
    status, result = http_json("POST", base_url, "/api/workflows/customer-worker-task", {
        "adapter": adapter,
        "confirm_run": True,
        "title": f"{DOGFOOD_TITLE} - {adapter}",
        "description": DOGFOOD_DESCRIPTION,
        "acceptance_criteria": DOGFOOD_ACCEPTANCE,
        "priority": "high",
        "risk_level": "medium",
        "selected_agent_ids": [f"agt_customer_worker_{adapter}"],
        "hermes_timeout": 300,
    })
    evidence = result.get("evidence") or {}
    require(status == 201, f"{adapter} live dogfood status mismatch: {status} {result}", failures)
    require(result.get("ok") is True, f"{adapter} live dogfood did not complete: {result}", failures)
    require(result.get("dry_run") is False, f"{adapter} live dogfood should not be dry-run: {result}", failures)
    require(bool(result.get("run_id")), f"{adapter} missing run id: {result}", failures)
    require(bool(result.get("artifact_id")), f"{adapter} missing artifact id: {result}", failures)
    require(evidence.get("tool_calls", 0) >= 1, f"{adapter} missing tool evidence: {evidence}", failures)
    require(evidence.get("evaluations", 0) >= 1, f"{adapter} missing eval evidence: {evidence}", failures)
    require(evidence.get("audit_logs", 0) >= 1, f"{adapter} missing audit evidence: {evidence}", failures)
    require(evidence.get("artifacts", 0) >= 1, f"{adapter} missing artifact evidence: {evidence}", failures)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local live Hermes/OpenClaw dogfood through customer worker workflow.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--adapter", action="append", choices=["hermes", "openclaw"], default=None)
    args = parser.parse_args()
    failures: list[str] = []
    adapters = args.adapter or ["hermes", "openclaw"]
    results = {adapter: run_adapter(args.base_url, adapter, failures) for adapter in adapters}
    serialized = json.dumps(results, ensure_ascii=False)
    require("agtok_" not in serialized and "agtsess_" not in serialized and "sk-" not in serialized and "ntn_" not in serialized, "dogfood output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "title": DOGFOOD_TITLE,
        "adapters": adapters,
        "runs": {adapter: result.get("run_id") for adapter, result in results.items()},
        "artifacts": {adapter: result.get("artifact_id") for adapter, result in results.items()},
        "evidence": {adapter: result.get("evidence") for adapter, result in results.items()},
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
