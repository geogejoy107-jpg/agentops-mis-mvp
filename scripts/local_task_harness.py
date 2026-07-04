#!/usr/bin/env python3
"""Plan or execute a local AgentOps MIS task through the existing worker harness.

The default mode is plan-only and does not require a running MIS server. Use
`--execute` to call `scripts/agentops workflow run-task`. Live Hermes/OpenClaw
execution still requires `--confirm-run`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
CLI_DISPLAY = "./scripts/agentops"
LIVE_ADAPTERS = {"hermes", "openclaw"}


SECRET_RE = re.compile(
    r"(Authorization:|Bearer |agtok_[A-Za-z0-9_-]{16,}|agtsess_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|ntn_[A-Za-z0-9_-]{16,}|github_pat_[A-Za-z0-9_]+|gh[opsu]_[A-Za-z0-9_]+)",
    re.IGNORECASE,
)


def utc_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def redact(value: str, limit: int = 500) -> str:
    compact = " ".join(str(value or "").split())
    return compact[:limit]


def shell_join(parts: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in parts)


def build_run_task_args(args: argparse.Namespace, worker_agent_id: str) -> list[str]:
    cli_args = [
        "workflow",
        "run-task",
        "--adapter",
        args.adapter,
        "--worker-agent-id",
        worker_agent_id,
        "--title",
        args.title,
        "--description",
        args.description,
        "--acceptance",
        args.acceptance,
        "--priority",
        args.priority,
        "--risk",
        args.risk,
    ]
    if args.confirm_run:
        cli_args.append("--confirm-run")
    return cli_args


def build_packet(args: argparse.Namespace, worker_agent_id: str) -> dict:
    run_args = build_run_task_args(args, worker_agent_id)
    base_command = [CLI_DISPLAY, *run_args]
    confirm_required = args.adapter in LIVE_ADAPTERS
    return {
        "packet_id": f"local_task_harness_{args.adapter}_{utc_stamp()}",
        "packet_kind": "local_task_harness_v1",
        "packet_version": "v1",
        "workspace_id": args.workspace_id,
        "task_id": None,
        "agent_id": worker_agent_id,
        "runtime_connector_id": f"rtc_{args.adapter}_local" if args.adapter != "mock" else "rtc_agent_gateway_mock",
        "objective_summary": redact(args.title, 180),
        "authority_refs": [
            "docs/HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md",
            "docs/V1_5_AGENT_WORKER_LOOP_SPEC.md",
            "docs/V1_5_AGENT_WORKER_ACCEPTANCE.md",
        ],
        "allowed_commands": [
            shell_join(base_command),
            shell_join([CLI_DISPLAY, "run", "get", "--run-id", "<run_id>"]),
            shell_join([CLI_DISPLAY, "run", "evidence-graph", "--run-id", "<run_id>"]),
            shell_join([CLI_DISPLAY, "artifact", "list", "--run-id", "<run_id>"]),
        ],
        "forbidden_actions": [
            "Do not store raw prompts or raw model responses.",
            "Do not commit local SQLite DBs, .env files, cache, dist, node_modules or generated runtime artifacts.",
            "Do not run Hermes/OpenClaw live adapters without --confirm-run.",
            "Do not treat mock evidence as product-readiness proof.",
        ],
        "required_gates": [
            "READ task and authority refs",
            "PLAN through Agent Plan and plan hash",
            "RETRIEVE scoped evidence if needed",
            "COMPARE against acceptance criteria",
            "EXECUTE through Agent Gateway CLI/API",
            "VERIFY run/tool/evaluation/artifact/audit evidence",
            "RECORD safe summaries, hashes and claim limits",
        ],
        "evidence_targets": [
            "task_id",
            "run_id",
            "agent_plan_id",
            "plan_evidence_manifest_id",
            "tool_calls",
            "evaluations",
            "runtime_events",
            "audit_logs",
            "artifacts",
            "memory_candidates",
        ],
        "verification_commands": [
            shell_join([CLI_DISPLAY, "workflow", "delivery-board", "--limit", "12"]),
            shell_join([CLI_DISPLAY, "run", "evidence-graph", "--run-id", "<run_id>"]),
            shell_join([CLI_DISPLAY, "operator", "runtime-doctor"]),
        ],
        "redaction_rules": {
            "raw_prompt_stored": False,
            "raw_response_stored": False,
            "credentials_stored": False,
            "private_transcripts_stored": False,
            "summary_only": True,
        },
        "claim_limit": (
            "real-runtime dogfood proof only for the returned adapter/run id"
            if args.confirm_run and confirm_required
            else "CI/offline or dry-run harness proof; not product-readiness proof for live runtimes"
        ),
        "confirm_required": confirm_required,
    }


def execute(args: argparse.Namespace, worker_agent_id: str) -> dict:
    cli_args = build_run_task_args(args, worker_agent_id)
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = args.base_url
    env["AGENTOPS_WORKSPACE_ID"] = args.workspace_id
    env["AGENTOPS_REQUEST_TIMEOUT"] = str(args.request_timeout)
    if args.confirm_run:
        env["HERMES_ALLOW_REAL_RUN"] = env.get("HERMES_ALLOW_REAL_RUN", "true")
    proc = subprocess.run(
        [str(CLI), *cli_args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=args.request_timeout + 30,
        check=False,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    secret_leaked = bool(SECRET_RE.search(stdout) or SECRET_RE.search(stderr))
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        payload = {
            "parse_error": True,
            "stdout_summary": redact(stdout, 500),
            "stderr_summary": redact(stderr, 500),
        }
    return {
        "executed": True,
        "returncode": proc.returncode,
        "ok": proc.returncode == 0 and not secret_leaked,
        "payload": payload,
        "secret_leaked": secret_leaked,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or execute a local AgentOps MIS task harness.")
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--title", default="Local task harness smoke task")
    parser.add_argument("--description", default="Run a bounded customer task through AgentOps MIS and record safe evidence.")
    parser.add_argument("--acceptance", default="Return task, run, plan, tool, evaluation, artifact and audit readback.")
    parser.add_argument("--priority", choices=["low", "medium", "high"], default="high")
    parser.add_argument("--risk", choices=["low", "medium", "high"], default="low")
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", "local-demo"))
    parser.add_argument("--worker-agent-id", default="")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--request-timeout", type=int, default=int(os.environ.get("AGENTOPS_REQUEST_TIMEOUT", "420")))
    parser.add_argument("--execute", action="store_true", help="Call scripts/agentops workflow run-task.")
    parser.add_argument("--confirm-run", action="store_true", help="Allow confirmed Hermes/OpenClaw live execution.")
    args = parser.parse_args(argv)

    worker_agent_id = args.worker_agent_id or f"agt_local_task_harness_{args.adapter}"
    packet = build_packet(args, worker_agent_id)
    result: dict = {
        "operation": "local_task_harness",
        "ok": True,
        "mode": "execute" if args.execute else "plan",
        "adapter": args.adapter,
        "confirm_run": bool(args.confirm_run),
        "base_url": args.base_url,
        "work_packet": packet,
        "safety": {
            "plan_only": not args.execute,
            "live_execution_performed": False,
            "ledger_mutated": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        },
    }
    if args.execute:
        execution = execute(args, worker_agent_id)
        payload = execution.get("payload") or {}
        result["execution"] = execution
        result["ok"] = bool(execution.get("ok"))
        result["safety"]["ledger_mutated"] = bool(payload.get("run_id") or payload.get("task_id"))
        result["safety"]["live_execution_performed"] = bool(args.adapter in LIVE_ADAPTERS and args.confirm_run and payload.get("dry_run") is not True)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
