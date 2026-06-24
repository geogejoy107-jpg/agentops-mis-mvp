#!/usr/bin/env python3
"""Run a hard-coded local Hermes/OpenClaw dogfood task through AgentOps MIS CLI.

This is intentionally CLI-first: the product proof is that a customer/operator
can dispatch work to machine-facing agents without pretending the agent is a
human clicking the browser UI.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"


DOGFOOD_TITLE = "通过 Agent Gateway CLI 让真实 Hermes / OpenClaw 优化 AgentOps MIS"
DOGFOOD_DESCRIPTION = (
    "请以外部 AI 数字员工的身份完成一次 AgentOps MIS 自举评审。客户/管理员只通过浏览器发布和查看任务，"
    "你必须假定 agent 通过 Agent Gateway CLI/API 接任务、claim、执行并回写 run/tool/eval/audit/artifact。"
    "目标是找出目前最影响真实客户用 agent 完成工作的 3-5 个问题，并给出下一步产品改进建议。"
    "不要请求外部联网，不要读取私聊或凭证，只基于任务说明和 MIS 运行上下文输出。"
)
DOGFOOD_ACCEPTANCE = (
    "必须给出可执行的产品建议；必须明确浏览器 UI 只服务客户/管理员，agent 执行必须走 CLI/API/MCP；"
    "必须说明哪些由 agent worker/adapter 解决，哪些由 MIS UI/权限/审计解决；必须写入 runs、tool_calls、"
    "evaluations、audit_logs、memory candidate、delivery approval 和 customer_worker_result artifact。"
)


def parse_json(raw: str) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def secret_leaked(text: str) -> bool:
    return bool(re.search(r"(Authorization:|Bearer |agtok_[A-Za-z0-9_-]{16,}|agtsess_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|ntn_[A-Za-z0-9_-]{16,})", text))


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def run_adapter(base_url: str, adapter: str, timeout: int, hermes_timeout: int, failures: list[str]) -> dict:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_WORKSPACE_ID"] = env.get("AGENTOPS_WORKSPACE_ID", "local-demo")
    env["AGENTOPS_REQUEST_TIMEOUT"] = str(timeout)
    worker_agent_id = f"agt_cli_dogfood_{adapter}_{os.getpid()}"
    proc = subprocess.run(
        [
            str(CLI),
            "workflow",
            "customer-worker-task",
            "--adapter",
            adapter,
            "--confirm-run",
            "--title",
            f"{DOGFOOD_TITLE} - {adapter}",
            "--description",
            DOGFOOD_DESCRIPTION,
            "--acceptance",
            DOGFOOD_ACCEPTANCE,
            "--priority",
            "high",
            "--risk",
            "medium",
            "--selected-agent-id",
            f"agt_customer_worker_{adapter}",
            "--worker-agent-id",
            worker_agent_id,
            "--hermes-timeout",
            str(hermes_timeout),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout + 30,
        check=False,
    )
    result = parse_json(proc.stdout)
    evidence = result.get("evidence") or {}
    require(proc.returncode == 0, f"{adapter} CLI exited {proc.returncode}: {proc.stderr or proc.stdout}", failures)
    require(result.get("provider") == "agentops-worker", f"{adapter} did not use worker provider: {result}", failures)
    require(result.get("workflow") == "customer_worker_task", f"{adapter} wrong workflow: {result}", failures)
    require(result.get("ok") is True, f"{adapter} live dogfood did not complete: {result}", failures)
    require(result.get("dry_run") is False, f"{adapter} live dogfood should not be dry-run: {result}", failures)
    require(result.get("adapter") == adapter, f"{adapter} adapter mismatch: {result}", failures)
    require(bool(result.get("run_id")), f"{adapter} missing run id: {result}", failures)
    require(bool(result.get("artifact_id")), f"{adapter} missing artifact id: {result}", failures)
    require(evidence.get("tool_calls", 0) >= 1, f"{adapter} missing tool evidence: {evidence}", failures)
    require(evidence.get("evaluations", 0) >= 1, f"{adapter} missing eval evidence: {evidence}", failures)
    require(evidence.get("audit_logs", 0) >= 1, f"{adapter} missing audit evidence: {evidence}", failures)
    require(evidence.get("artifacts", 0) >= 1, f"{adapter} missing artifact evidence: {evidence}", failures)
    require(evidence.get("memories", 0) >= 1, f"{adapter} missing memory evidence: {evidence}", failures)
    require(evidence.get("approvals", 0) >= 1, f"{adapter} missing approval evidence: {evidence}", failures)
    require(not secret_leaked(proc.stdout + proc.stderr), f"{adapter} CLI output leaked token-like material", failures)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local live Hermes/OpenClaw dogfood through customer worker workflow.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--adapter", action="append", choices=["hermes", "openclaw"], default=None)
    parser.add_argument("--request-timeout", type=int, default=420)
    parser.add_argument("--hermes-timeout", type=int, default=300)
    args = parser.parse_args()
    failures: list[str] = []
    adapters = args.adapter or ["hermes", "openclaw"]
    results = {adapter: run_adapter(args.base_url, adapter, args.request_timeout, args.hermes_timeout, failures) for adapter in adapters}
    serialized = json.dumps(results, ensure_ascii=False)
    require(not secret_leaked(serialized), "dogfood output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "title": DOGFOOD_TITLE,
        "execution_contract": "customer/operator uses browser for oversight; agents use Agent Gateway CLI/API for execution",
        "adapters": adapters,
        "runs": {adapter: result.get("run_id") for adapter, result in results.items()},
        "artifacts": {adapter: result.get("artifact_id") for adapter, result in results.items()},
        "evidence": {adapter: result.get("evidence") for adapter, result in results.items()},
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
