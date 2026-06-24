#!/usr/bin/env python3
"""Run a fixed customer template through real Hermes/OpenClaw worker adapters."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"

LIVE_TITLE = "模板任务真实执行：优化 AgentOps MIS 客户工作台"
LIVE_DESCRIPTION = (
    "请以客户视角审视 AgentOps MIS 当前任务创建、AI 员工、Run Ledger、审批、评估和报告闭环，"
    "提出 3-5 个可执行改进建议。不要读取私聊或凭证，不要联网。"
)
LIVE_ACCEPTANCE = (
    "必须写入 run、tool、evaluation、audit、artifact、memory candidate 和 pending delivery approval 证据。"
)


def run_cli(adapter: str, timeout: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.setdefault("AGENTOPS_REQUEST_TIMEOUT", str(timeout))
    return subprocess.run(
        [
            str(CLI),
            "workflow",
            "run-template",
            "--template-id",
            "tpl_customer_ui_review",
            "--adapter",
            adapter,
            "--confirm-run",
            "--hermes-timeout",
            "300",
            "--request-timeout",
            str(timeout),
            "--title",
            f"{LIVE_TITLE} - {adapter}",
            "--description",
            LIVE_DESCRIPTION,
            "--acceptance",
            LIVE_ACCEPTANCE,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout + 30,
        check=False,
    )


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def parse_json(raw: str) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def token_like_leaked(text: str) -> bool:
    return any(marker in text for marker in ["Authorization:", "Bearer ", "agtok_", "agtsess_", "ntn_", "sk-"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live template worker dogfood through Hermes/OpenClaw.")
    parser.add_argument("--adapter", action="append", choices=["hermes", "openclaw"], default=None)
    parser.add_argument("--request-timeout", type=int, default=420)
    args = parser.parse_args()
    adapters = args.adapter or ["hermes", "openclaw"]
    failures: list[str] = []
    results: dict[str, dict] = {}
    raw_output = []

    for adapter in adapters:
        proc = run_cli(adapter, args.request_timeout)
        raw_output.extend([proc.stdout, proc.stderr])
        payload = parse_json(proc.stdout)
        evidence = payload.get("evidence") or {}
        results[adapter] = payload
        require(proc.returncode == 0, f"{adapter} CLI exited {proc.returncode}: {proc.stderr or proc.stdout}", failures)
        require(payload.get("provider") == "agentops-worker", f"{adapter} did not use worker provider: {payload}", failures)
        require(payload.get("workflow") == "customer_worker_task", f"{adapter} wrong workflow: {payload}", failures)
        require(payload.get("ok") is True, f"{adapter} did not complete: {payload}", failures)
        require(payload.get("dry_run") is False, f"{adapter} should be live, not dry-run: {payload}", failures)
        require((payload.get("template_execution") or {}).get("adapter") == adapter, f"{adapter} missing template adapter metadata: {payload}", failures)
        require(bool(payload.get("run_id")), f"{adapter} missing run id: {payload}", failures)
        require(bool(payload.get("artifact_id")), f"{adapter} missing artifact id: {payload}", failures)
        require(evidence.get("tool_calls", 0) >= 1, f"{adapter} missing tool evidence: {evidence}", failures)
        require(evidence.get("evaluations", 0) >= 1, f"{adapter} missing eval evidence: {evidence}", failures)
        require(evidence.get("audit_logs", 0) >= 1, f"{adapter} missing audit evidence: {evidence}", failures)
        require(evidence.get("artifacts", 0) >= 1, f"{adapter} missing artifact evidence: {evidence}", failures)
        require(evidence.get("memories", 0) >= 1, f"{adapter} missing memory evidence: {evidence}", failures)
        require(evidence.get("approvals", 0) >= 1, f"{adapter} missing approval evidence: {evidence}", failures)

    require(not token_like_leaked("\n".join(raw_output)), "live dogfood output leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "template_id": "tpl_customer_ui_review",
        "adapters": adapters,
        "runs": {adapter: payload.get("run_id") for adapter, payload in results.items()},
        "artifacts": {adapter: payload.get("artifact_id") for adapter, payload in results.items()},
        "evidence": {adapter: payload.get("evidence") for adapter, payload in results.items()},
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
