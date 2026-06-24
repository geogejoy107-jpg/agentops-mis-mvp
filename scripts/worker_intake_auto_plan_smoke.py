#!/usr/bin/env python3
"""Verify workers can safely auto-plan intake-blocked assigned tasks."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentops_mis_cli import worker  # noqa: E402


TOKEN_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+(?!\\[REDACTED\\])[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"agtok_[A-Za-z0-9_-]{16,}"),
    re.compile(r"agtsess_[A-Za-z0-9_-]{16,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9_-]{8,}"),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in TOKEN_PATTERNS)


class AutoPlanClient:
    workspace_id = "local-demo"
    agent_id = "agt_worker_auto_plan_openclaw"
    api_key = ""

    def __init__(self, *, risk_level: str = "low", plan_id: str | None = None) -> None:
        self.risk_level = risk_level
        self.plan_id = plan_id
        self.gets: list[tuple[str, dict | None]] = []
        self.posts: list[tuple[str, dict]] = []

    def get(self, path: str, query: dict | None = None):
        self.gets.append((path, query))
        if path == "/api/agent-gateway/tasks/pull":
            failed = ["verified_agent_plan"] if self.plan_id else ["agent_plan", "verified_agent_plan", "knowledge_retrieval", "base_reference"]
            return {
                "tasks": [],
                "intake": {
                    "blocked": 1,
                    "next_actions": ["agentops knowledge search \"Auto plan smoke\" --limit 10"],
                    "blocked_tasks": [
                        {
                            "task_id": "tsk_worker_auto_plan_smoke",
                            "title": "Auto plan smoke",
                            "status": "planned",
                            "priority": "medium",
                            "risk_level": self.risk_level,
                            "assigned_adapter": "openclaw",
                            "assigned_agent_ids": [self.agent_id],
                            "plan_id": self.plan_id,
                            "failed_gate_ids": failed,
                            "token_omitted": True,
                        }
                    ],
                    "token_omitted": True,
                },
            }
        if path == "/api/agent-gateway/tasks/tsk_worker_auto_plan_smoke":
            return {
                "task": {
                    "task_id": "tsk_worker_auto_plan_smoke",
                    "title": "Auto plan smoke",
                    "description": "Worker should create a verified Agent Plan before pulling this assigned task.",
                    "acceptance_criteria": "No run_start or adapter execution happens during intake auto-plan.",
                    "risk_level": self.risk_level,
                },
                "token_omitted": True,
            }
        if path == "/api/agent-gateway/knowledge/evidence-packet":
            return {
                "operation": "knowledge_retrieval_evidence_packet",
                "status": "ready",
                "query_hash": "kqh_auto_plan_smoke",
                "packet_hash": "kph_auto_plan_smoke",
                "metrics": {"recall_at_5": 1.0, "mrr": 1.0},
                "task_context": {
                    "task_id": "tsk_worker_auto_plan_smoke",
                    "task_found": True,
                    "query_source": "task_id",
                    "source_fields": ["title", "description", "acceptance_criteria", "risk_level"],
                    "task_text_omitted": True,
                    "token_omitted": True,
                },
                "primary_search": {
                    "results": [
                        {
                            "retrieval_id": "kret_auto_plan",
                            "doc_id": "doc_project_spec",
                            "chunk_id": "chunk_project_spec",
                            "path": "docs/AGENT_WORK_METHOD_BLOCK.md",
                            "source_hash": "source_hash_auto_plan",
                            "rank": 1,
                        }
                    ]
                },
                "token_omitted": True,
            }
        if path.startswith("/api/agent-gateway/agent-plans/") and path.endswith("/verify"):
            return {"verification": {"pass": True, "failed_checks": [], "token_omitted": True}, "token_omitted": True}
        raise AssertionError(f"unexpected GET {path} {query}")

    def post(self, path: str, payload: dict, timeout: int = 180):
        self.posts.append((path, payload))
        if path == "/api/agent-gateway/agent-plans":
            return {"agent_plan": {"plan_id": "plan_worker_auto_plan_smoke"}, "token_omitted": True}
        if path == "/api/agent-gateway/audit":
            return {"audit": {"audit_id": "aud_worker_auto_plan_smoke"}, "token_omitted": True}
        raise AssertionError(f"unexpected POST {path} {payload}")


def run_auto_create_case(failures: list[str]) -> dict:
    args = worker.build_parser().parse_args(["--once", "--adapter", "openclaw", "--confirm-run"])
    client = AutoPlanClient(risk_level="low")
    result = worker.process_one_task(client, args)
    plan_posts = [payload for path, payload in client.posts if path == "/api/agent-gateway/agent-plans"]
    audit_posts = [payload for path, payload in client.posts if path == "/api/agent-gateway/audit"]
    require(result.get("reason") == "intake_auto_planned", f"auto-plan reason mismatch: {result}", failures)
    require(result.get("processed") is False, f"auto-plan must not count as task execution: {result}", failures)
    require(result.get("run_start_attempted") is False, f"auto-plan must not start run: {result}", failures)
    require(result.get("live_execution_performed") is False, f"auto-plan must not execute live runtime: {result}", failures)
    require(result.get("plan_id") == "plan_worker_auto_plan_smoke", f"plan id missing: {result}", failures)
    require(bool(plan_posts), "agent plan was not created", failures)
    if plan_posts:
        payload = plan_posts[0]
        require(payload.get("referenced_specs"), f"plan missing referenced specs: {payload}", failures)
        require(payload.get("referenced_memories"), f"plan missing referenced memories: {payload}", failures)
        require(payload.get("referenced_bases") == ["base_local_tasks", "base_local_memory"], f"plan bases mismatch: {payload}", failures)
        require(payload.get("execution_steps") == ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"], f"plan steps mismatch: {payload}", failures)
    require(bool(audit_posts), "auto-plan audit missing", failures)
    return result


def run_existing_verify_case(failures: list[str]) -> dict:
    args = worker.build_parser().parse_args(["--once", "--adapter", "openclaw", "--confirm-run"])
    client = AutoPlanClient(risk_level="low", plan_id="plan_existing_auto_plan_smoke")
    result = worker.process_one_task(client, args)
    plan_posts = [payload for path, payload in client.posts if path == "/api/agent-gateway/agent-plans"]
    require(result.get("reason") == "intake_plan_verified", f"existing plan verify reason mismatch: {result}", failures)
    require(result.get("processed") is False, f"verify-only must not count as task execution: {result}", failures)
    require(result.get("plan_id") == "plan_existing_auto_plan_smoke", f"existing plan id mismatch: {result}", failures)
    require(not plan_posts, f"verify-only should not create a duplicate plan: {plan_posts}", failures)
    return result


def run_intake_reuse_helper_case(failures: list[str]) -> dict:
    client = AutoPlanClient(risk_level="low", plan_id="plan_existing_auto_plan_smoke")
    plan_id, verified = worker.verified_intake_plan_for_task(client, {
        "task_id": "tsk_worker_auto_plan_smoke",
        "intake": {
            "plan_id": "plan_existing_auto_plan_smoke",
            "plan_verified": True,
            "token_omitted": True,
        },
    })
    require(plan_id == "plan_existing_auto_plan_smoke", f"verified intake plan was not reused: {plan_id} {verified}", failures)
    require((verified or {}).get("verification", {}).get("pass") is True, f"verified intake plan did not pass: {verified}", failures)
    require(not client.posts, f"reuse helper should not mutate ledger: {client.posts}", failures)
    return {"plan_id": plan_id, "verification_pass": (verified or {}).get("verification", {}).get("pass")}


def run_high_risk_case(failures: list[str]) -> dict:
    args = worker.build_parser().parse_args(["--once", "--adapter", "openclaw", "--confirm-run"])
    client = AutoPlanClient(risk_level="critical")
    result = worker.process_one_task(client, args)
    plan_posts = [payload for path, payload in client.posts if path == "/api/agent-gateway/agent-plans"]
    require(result.get("reason") == "intake_auto_plan_risk_blocked", f"high-risk block reason mismatch: {result}", failures)
    require(result.get("processed") is False, f"high-risk block must not count as task execution: {result}", failures)
    require(not plan_posts, f"high-risk task should not be auto-planned without allow-high-risk: {plan_posts}", failures)
    return result


def main() -> int:
    failures: list[str] = []
    create_result = run_auto_create_case(failures)
    verify_result = run_existing_verify_case(failures)
    reuse_result = run_intake_reuse_helper_case(failures)
    high_risk_result = run_high_risk_case(failures)
    serialized = json.dumps({
        "create": create_result,
        "verify": verify_result,
        "reuse": reuse_result,
        "high_risk": high_risk_result,
    }, ensure_ascii=False)
    require(not leaked(serialized), "worker intake auto-plan leaked token-like material", failures)
    print(json.dumps({
        "ok": not failures,
        "operation": "worker_intake_auto_plan_smoke",
        "auto_create_reason": create_result.get("reason"),
        "existing_verify_reason": verify_result.get("reason"),
        "intake_reuse_plan_id": reuse_result.get("plan_id"),
        "high_risk_reason": high_risk_result.get("reason"),
        "live_execution_performed": False,
        "secret_leaked": leaked(serialized),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
