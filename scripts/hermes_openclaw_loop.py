#!/usr/bin/env python3
"""Supervise a clean Hermes <-> OpenClaw collaboration loop.

The script is intentionally outside the product path: it coordinates local
runtime reviewers and writes only redacted loop metadata to a gitignored runtime
directory. Default mode is dry-run so the loop can be smoke-tested without live
runtime calls.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_DIR = ROOT / ".agentops_runtime" / "loops"
DEFAULT_BASE_URL = "http://127.0.0.1:8787"
DEFAULT_WORKSPACE_ID = "local-demo"
SECRET_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[a-z0-9._\-]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(token|secret|password|api[_-]?key)\s*[:=]\s*['\"]?[^'\"\s,;]+"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)\b(?:sk-[a-z0-9._\-]+|ntn_[a-z0-9._\-]+|agtok_[a-z0-9_]+|agtsess_[a-z0-9_]+)\b"), "[SECRET_REDACTED]"),
]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def stable_hash(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def redact(text: str | None, limit: int = 800) -> str:
    value = str(text or "")
    for pattern, repl in SECRET_PATTERNS:
        value = pattern.sub(repl, value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def stable_id(prefix: str, *parts) -> str:
    return f"{prefix}_{stable_hash(parts)[:16]}"


class GatewayClient:
    def __init__(self, base_url: str, workspace_id: str, api_key: str = "", timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.workspace_id = workspace_id
        self.api_key = api_key or ""
        self.timeout = timeout

    def post(self, path: str, payload: dict, agent_id: str = "") -> dict:
        headers = {
            "Content-Type": "application/json",
            "X-AgentOps-Workspace-Id": self.workspace_id,
        }
        if agent_id:
            headers["X-AgentOps-Agent-Id"] = agent_id
        if self.api_key:
            headers["X-AgentOps-Api-Key"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"POST {path} failed: {exc.code} {redact(detail, 500)}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach {self.base_url}{path}: {redact(str(exc.reason), 300)}") from exc


AGENT_WORK_STEPS = ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"]


def loop_prompt(topic: str, round_no: int, previous: list[dict]) -> str:
    prior = []
    for item in previous[-4:]:
        prior.append(f"{item['agent']}({item['status']}): {item.get('summary', '')}")
    prior_text = "\n".join(prior) if prior else "No prior loop output."
    return (
        "You are participating in a supervised Hermes/OpenClaw engineering loop.\n"
        "Do not request or output secrets. Do not edit files. Return concise JSON only.\n"
        "Focus on enabling the two runtimes to loop cleanly under Codex supervision.\n"
        f"Round: {round_no}\n"
        f"Topic: {topic}\n"
        f"Prior outputs:\n{prior_text}\n"
        "JSON schema: {\"ok\":true|false,\"finding\":\"...\",\"next_action\":\"...\",\"risk\":\"low|medium|high\"}"
    )


def call_hermes(prompt: str, args) -> dict:
    payload = {
        "model": args.hermes_model,
        "messages": [
            {"role": "system", "content": "You are Hermes in a supervised local engineering loop. Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": args.max_tokens,
    }
    req = urllib.request.Request(
        args.hermes_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=args.hermes_timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return {
        "status": "completed",
        "summary": redact((body.get("choices") or [{}])[0].get("message", {}).get("content", "")),
        "raw_omitted": True,
    }


def call_openclaw(prompt: str, args) -> dict:
    proc = subprocess.run(
        [
            args.openclaw_bin,
            "agent",
            "--agent",
            args.openclaw_agent,
            "-m",
            prompt,
            "--timeout",
            str(args.openclaw_timeout),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=args.openclaw_timeout + 20,
        check=False,
    )
    return {
        "status": "completed" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "summary": redact(proc.stdout or proc.stderr),
        "raw_omitted": True,
    }


def dry_result(agent: str, prompt: str) -> dict:
    return {
        "status": "dry_run",
        "summary": f"{agent} live call skipped. prompt_hash={stable_hash(prompt)[:16]}",
        "raw_omitted": True,
    }


def forced_failure_result(agent: str, prompt: str) -> dict:
    return {
        "status": "failed",
        "summary": f"{agent} forced failure for loop smoke. prompt_hash={stable_hash(prompt)[:16]}",
        "raw_omitted": True,
        "error_type": "ForcedLoopFailure",
        "retryable": False,
    }


def secret_like(text: str | None) -> bool:
    value = str(text or "")
    return any(pattern.search(value) for pattern, _repl in SECRET_PATTERNS)


def evaluate_output(row: dict) -> dict:
    checks = [
        {"id": "status_ok", "ok": row.get("status") in {"completed", "dry_run"}},
        {"id": "raw_omitted", "ok": row.get("raw_omitted") is True},
        {"id": "summary_present", "ok": bool(row.get("summary"))},
        {"id": "no_secret_like_output", "ok": not secret_like(row.get("summary"))},
        {"id": "prompt_hashed", "ok": bool(row.get("prompt_hash")) and "prompt" not in row},
    ]
    passed = sum(1 for check in checks if check["ok"])
    score = round(passed / len(checks), 3)
    return {
        "pass": score == 1.0,
        "score": score,
        "checks": checks,
        "failed_checks": [check["id"] for check in checks if not check["ok"]],
        "evaluator": "codex_loop_rule_v1",
    }


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def git_check_ignored(path: Path) -> bool:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", str(path)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def audit_event(audit_path: Path, loop_id: str, action: str, entity_type: str, entity_id: str, metadata: dict) -> None:
    row = {
        "audit_id": "aud_loop_" + stable_hash({"loop_id": loop_id, "action": action, "entity_id": entity_id, "at": now_iso()})[:16],
        "loop_id": loop_id,
        "actor_type": "system",
        "actor_id": "codex-loop-supervisor",
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "metadata": metadata,
        "raw_omitted": True,
        "created_at": now_iso(),
    }
    append_jsonl(audit_path, row)


def gateway_agent_plan(client: GatewayClient, args, agent_id: str, task_id: str, run_id: str | None, understanding: str, risk: str, files: list[str]) -> dict:
    return client.post("/api/agent-gateway/agent-plans", {
        "workspace_id": args.workspace_id,
        "agent_id": agent_id,
        "task_id": task_id,
        "run_id": run_id,
        "task_understanding": understanding,
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md", "docs/AGENT_WORK_METHOD_BLOCK.md", "docs/HERMES_OPENCLAW_LOOP_RUNBOOK.md"],
        "referenced_memories": ["knowledge/shared/common_failures.md", "project_memory"],
        "referenced_bases": ["knowledge/bases/hermes/BASE_SPEC.md", "knowledge/bases/openclaw/BASE_SPEC.md", "agent_gateway_ledger"],
        "proposed_files_to_change": files,
        "risk_level": risk,
        "approval_required": risk in {"high", "critical"},
        "execution_steps": AGENT_WORK_STEPS,
        "verification_plan": "Loop lane must record tool, evaluation, artifact, audit and plan_evidence_manifest evidence for this run.",
        "rollback_plan": "Leave the loop blocked, keep runtime files under .agentops_runtime, and require Codex/operator review before another live iteration.",
        "status": "submitted",
    }, agent_id=agent_id)


def gateway_plan_manifest(client: GatewayClient, args, agent_id: str, plan_id: str, run_id: str, tool_call_id: str | None, evaluation_id: str | None, artifact_id: str | None) -> dict:
    return client.post("/api/agent-gateway/plan-evidence-manifests", {
        "workspace_id": args.workspace_id,
        "agent_id": agent_id,
        "plan_id": plan_id,
        "run_id": run_id,
        "mismatch_policy": "block",
        "expected_steps": AGENT_WORK_STEPS,
        "tool_call_ids": [tool_call_id] if tool_call_id else [],
        "evaluation_ids": [evaluation_id] if evaluation_id else [],
        "artifact_ids": [artifact_id] if artifact_id else [],
    }, agent_id=agent_id)


def record_loop_to_mis(args, loop_id: str, outputs: list[dict], artifact: dict) -> dict:
    client = GatewayClient(args.base_url, args.workspace_id, args.api_key, args.request_timeout)
    supervisor_id = stable_id("agt_loop_supervisor", args.workspace_id, "hermes-openclaw")
    agent_ids = {
        "hermes": stable_id("agt_loop_hermes", args.workspace_id),
        "openclaw": stable_id("agt_loop_openclaw", args.workspace_id),
    }
    registered_agents = []
    for agent_id, name, role, runtime_type in [
        (supervisor_id, "Codex Loop Supervisor", "Loop Supervisor", "codex"),
        (agent_ids["hermes"], "Hermes Loop Reviewer", "Hermes Runtime Reviewer", "hermes"),
        (agent_ids["openclaw"], "OpenClaw Loop Reviewer", "OpenClaw Runtime Reviewer", "openclaw"),
    ]:
        client.post("/api/agent-gateway/register", {
            "workspace_id": args.workspace_id,
            "agent_id": agent_id,
            "name": name,
            "role": role,
            "runtime_type": runtime_type,
            "model_provider": runtime_type,
            "model_name": "supervised-loop",
            "allowed_tools": [
                "agent_gateway.tasks",
                "agent_gateway.runs",
                "agent_gateway.toolcalls",
                "agent_gateway.evaluations",
                "agent_gateway.audit",
                "agent_gateway.artifacts",
            ],
            "description": "Registered by the supervised Hermes/OpenClaw MIS loop harness.",
        }, agent_id=agent_id)
        registered_agents.append(agent_id)

    parent_task_id = stable_id("tsk_loop", loop_id)
    parent_run_id = stable_id("run_loop", loop_id, "supervisor")
    client.post("/api/agent-gateway/tasks", {
        "workspace_id": args.workspace_id,
        "task_id": parent_task_id,
        "title": f"Hermes/OpenClaw supervised loop: {redact(args.topic, 80)}",
        "description": f"Coordinate Hermes and OpenClaw through MIS ledger evidence. topic_hash={stable_hash(args.topic)[:16]}",
        "requester_id": "usr_founder",
        "owner_agent_id": supervisor_id,
        "collaborator_agent_ids": [agent_ids[item] for item in args.order],
        "status": "planned",
        "priority": "medium",
        "risk_level": "medium" if args.mode == "dry-run" else "high",
        "acceptance_criteria": "Every loop output must write run, tool-call, evaluation, audit and final artifact evidence without storing raw prompts or responses.",
    }, agent_id=supervisor_id)
    parent_plan = gateway_agent_plan(
        client,
        args,
        supervisor_id,
        parent_task_id,
        None,
        f"Supervise Hermes/OpenClaw loop {loop_id}, enforce bounded attempts, record child evidence and produce next action.",
        "medium" if args.mode == "dry-run" else "high",
        ["scripts/hermes_openclaw_loop.py", ".agentops_runtime/loops", "Agent Gateway ledger"],
    )
    parent_plan_id = (parent_plan.get("agent_plan") or {}).get("plan_id")
    client.post("/api/agent-gateway/runs/start", {
        "workspace_id": args.workspace_id,
        "run_id": parent_run_id,
        "task_id": parent_task_id,
        "agent_id": supervisor_id,
        "runtime_type": "codex",
        "input_summary": f"Supervised loop started. topic_hash={stable_hash(args.topic)[:16]}",
        "delegation_id": stable_id("del_loop", loop_id, "supervisor"),
    }, agent_id=supervisor_id)

    child_task_ids = []
    child_run_ids = []
    plan_ids = [parent_plan_id] if parent_plan_id else []
    manifest_ids = []
    verified_manifest_ids = []
    blocked_manifest_ids = []
    tool_call_ids = []
    evaluation_ids = []
    artifact_ids = []
    for row in outputs:
        agent = row["agent"]
        agent_id = agent_ids[agent]
        task_id = stable_id("tsk_loop", loop_id, agent, row["round"])
        run_id = stable_id("run_loop", loop_id, agent, row["round"])
        child_task_ids.append(task_id)
        child_run_ids.append(run_id)
        client.post("/api/agent-gateway/tasks", {
            "workspace_id": args.workspace_id,
            "task_id": task_id,
            "title": f"{agent} loop round {row['round']}",
            "description": f"Respond to supervised loop topic_hash={stable_hash(args.topic)[:16]} and prior summaries only.",
            "requester_id": "usr_founder",
            "owner_agent_id": agent_id,
            "collaborator_agent_ids": [supervisor_id],
            "status": "planned",
            "priority": "medium",
            "risk_level": "low" if row["status"] == "dry_run" else "medium",
            "acceptance_criteria": "Return a concise redacted summary; raw prompt and raw response must remain omitted.",
        }, agent_id=agent_id)
        child_plan = gateway_agent_plan(
            client,
            args,
            agent_id,
            task_id,
            None,
            f"{agent} loop round {row['round']} must review the topic using only redacted prior summaries and return safe loop guidance.",
            "low" if row["status"] == "dry_run" else "medium",
            ["scripts/hermes_openclaw_loop.py", ".agentops_runtime/loops"],
        )
        child_plan_id = (child_plan.get("agent_plan") or {}).get("plan_id")
        if child_plan_id:
            plan_ids.append(child_plan_id)
        client.post("/api/agent-gateway/runs/start", {
            "workspace_id": args.workspace_id,
            "run_id": run_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "runtime_type": agent,
            "input_summary": f"Loop round {row['round']} prompt_hash={row['prompt_hash'][:16]}",
            "parent_run_id": parent_run_id,
            "delegation_id": stable_id("del_loop", loop_id, agent, row["round"]),
        }, agent_id=agent_id)
        tool = client.post("/api/agent-gateway/tool-calls", {
            "workspace_id": args.workspace_id,
            "run_id": run_id,
            "agent_id": agent_id,
            "tool_name": "hermes.chat_completion" if agent == "hermes" else "openclaw.agent",
            "tool_category": "custom",
            "risk_level": "low" if row["status"] == "dry_run" else "medium",
            "status": "completed" if row["status"] in {"completed", "dry_run"} else "failed",
            "target_resource": f"loop://{loop_id}/{agent}/{row['round']}",
            "args": {"prompt_hash": row["prompt_hash"], "raw_prompt_omitted": True},
            "result_summary": row.get("summary") or row["status"],
        }, agent_id=agent_id)
        tool_call_id = (tool.get("tool_call") or {}).get("tool_call_id")
        if tool_call_id:
            tool_call_ids.append(tool_call_id)
        evaluation = row.get("evaluation") or evaluate_output(row)
        eval_payload = client.post("/api/agent-gateway/evaluations/submit", {
            "workspace_id": args.workspace_id,
            "run_id": run_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "evaluator_type": "rule",
            "score": evaluation.get("score", 0),
            "pass_fail": "pass" if evaluation.get("pass") else "fail",
            "rubric": {"gate": "hermes_openclaw_loop_v1", "checks": evaluation.get("checks") or []},
            "notes": f"Loop output evaluation for {agent} round {row['round']}.",
        }, agent_id=agent_id)
        evaluation_id = (eval_payload.get("evaluation") or {}).get("evaluation_id")
        if evaluation_id:
            evaluation_ids.append(evaluation_id)
        artifact_payload = client.post("/api/agent-gateway/artifacts", {
            "workspace_id": args.workspace_id,
            "run_id": run_id,
            "task_id": task_id,
            "agent_id": agent_id,
            "artifact_id": stable_id("art_loop_output", loop_id, agent, row["round"]),
            "artifact_type": "loop_agent_output",
            "title": f"{agent} loop round {row['round']} evidence",
            "uri": f"loop://{loop_id}/{agent}/{row['round']}",
            "summary": row.get("summary") or row["status"],
            "content_hash": stable_hash({
                "loop_id": loop_id,
                "agent": agent,
                "round": row["round"],
                "summary": row.get("summary") or "",
                "status": row.get("status"),
                "prompt_hash": row.get("prompt_hash"),
            }),
        }, agent_id=agent_id)
        artifact_id = (artifact_payload.get("artifact") or {}).get("artifact_id")
        if artifact_id:
            artifact_ids.append(artifact_id)
        client.post("/api/agent-gateway/audit", {
            "workspace_id": args.workspace_id,
            "agent_id": agent_id,
            "task_id": task_id,
            "run_id": run_id,
            "action": "loop.agent_output_recorded",
            "entity_type": "runs",
            "entity_id": run_id,
            "metadata": {
                "loop_id": loop_id,
                "round": row["round"],
                "agent": agent,
                "status": row["status"],
                "prompt_hash": row["prompt_hash"],
                "raw_omitted": True,
            },
        }, agent_id=agent_id)
        client.post(f"/api/agent-gateway/runs/{run_id}/heartbeat", {
            "workspace_id": args.workspace_id,
            "status": "completed" if row["status"] in {"completed", "dry_run"} and evaluation.get("pass") else "failed",
            "output_summary": row.get("summary") or row["status"],
            "duration_ms": 0,
            "error_type": None if evaluation.get("pass") else "LoopEvaluationFailed",
            "error_message": None if evaluation.get("pass") else ",".join(evaluation.get("failed_checks") or []),
        }, agent_id=agent_id)
        if child_plan_id:
            manifest_payload = gateway_plan_manifest(client, args, agent_id, child_plan_id, run_id, tool_call_id, evaluation_id, artifact_id)
            manifest = manifest_payload.get("manifest") or {}
            verification = manifest_payload.get("verification") or {}
            manifest_id = manifest.get("manifest_id")
            if manifest_id:
                manifest_ids.append(manifest_id)
                (verified_manifest_ids if verification.get("pass") else blocked_manifest_ids).append(manifest_id)

    artifact_payload = client.post("/api/agent-gateway/artifacts", {
        "workspace_id": args.workspace_id,
        "run_id": parent_run_id,
        "task_id": parent_task_id,
        "agent_id": supervisor_id,
        "artifact_id": stable_id("art_loop", loop_id),
        "artifact_type": "loop_next_action",
        "title": "Hermes/OpenClaw loop next action",
        "uri": f"loop://{loop_id}",
        "summary": artifact.get("recommended_next_action") or artifact.get("status") or "Loop artifact recorded.",
        "content_hash": stable_hash(artifact),
    }, agent_id=supervisor_id)
    parent_artifact_id = (artifact_payload.get("artifact") or {}).get("artifact_id")
    if parent_artifact_id:
        artifact_ids.append(parent_artifact_id)
    parent_tool = client.post("/api/agent-gateway/tool-calls", {
        "workspace_id": args.workspace_id,
        "run_id": parent_run_id,
        "agent_id": supervisor_id,
        "tool_name": "loop.supervise",
        "tool_category": "custom",
        "risk_level": "low" if args.mode == "dry-run" else "medium",
        "status": "completed" if artifact.get("status") == "ready_for_codex_review" else "failed",
        "target_resource": f"loop://{loop_id}",
        "args": {"loop_id": loop_id, "raw_prompt_omitted": True, "child_runs": len(child_run_ids)},
        "result_summary": artifact.get("recommended_next_action") or artifact.get("status") or "Loop supervised.",
    }, agent_id=supervisor_id)
    parent_tool_call_id = (parent_tool.get("tool_call") or {}).get("tool_call_id")
    if parent_tool_call_id:
        tool_call_ids.append(parent_tool_call_id)
    parent_eval = client.post("/api/agent-gateway/evaluations/submit", {
        "workspace_id": args.workspace_id,
        "run_id": parent_run_id,
        "task_id": parent_task_id,
        "agent_id": supervisor_id,
        "evaluator_type": "rule",
        "score": 1.0 if artifact.get("status") == "ready_for_codex_review" else 0.5,
        "pass_fail": "pass" if artifact.get("status") == "ready_for_codex_review" else "fail",
        "rubric": {"gate": "loop_parent_artifact_recorded", "raw_omitted": True},
        "notes": "Parent loop run recorded child evidence and final next-action artifact.",
    }, agent_id=supervisor_id)
    parent_evaluation_id = (parent_eval.get("evaluation") or {}).get("evaluation_id")
    if parent_evaluation_id:
        evaluation_ids.append(parent_evaluation_id)
    client.post("/api/agent-gateway/audit", {
        "workspace_id": args.workspace_id,
        "agent_id": supervisor_id,
        "task_id": parent_task_id,
        "run_id": parent_run_id,
        "action": "loop.completed",
        "entity_type": "runs",
        "entity_id": parent_run_id,
        "metadata": {
            "loop_id": loop_id,
            "child_runs": len(child_run_ids),
            "artifact_id": parent_artifact_id,
            "raw_omitted": True,
        },
    }, agent_id=supervisor_id)
    parent_ok = all((row.get("evaluation") or {}).get("pass") and row.get("status") in {"completed", "dry_run"} for row in outputs)
    client.post(f"/api/agent-gateway/runs/{parent_run_id}/heartbeat", {
        "workspace_id": args.workspace_id,
        "status": "completed" if parent_ok else "failed",
        "output_summary": artifact.get("recommended_next_action") or "Loop complete.",
        "duration_ms": 0,
        "error_type": None if parent_ok else "LoopChildFailure",
        "error_message": None if parent_ok else "One or more child loop evaluations failed.",
    }, agent_id=supervisor_id)
    if parent_plan_id:
        parent_manifest_payload = gateway_plan_manifest(client, args, supervisor_id, parent_plan_id, parent_run_id, parent_tool_call_id, parent_evaluation_id, parent_artifact_id)
        parent_manifest = parent_manifest_payload.get("manifest") or {}
        parent_verification = parent_manifest_payload.get("verification") or {}
        parent_manifest_id = parent_manifest.get("manifest_id")
        if parent_manifest_id:
            manifest_ids.append(parent_manifest_id)
            (verified_manifest_ids if parent_verification.get("pass") else blocked_manifest_ids).append(parent_manifest_id)
    return {
        "enabled": True,
        "ok": True,
        "provider": "agentops-mis",
        "workspace_id": args.workspace_id,
        "parent_task_id": parent_task_id,
        "parent_run_id": parent_run_id,
        "child_task_ids": child_task_ids,
        "child_run_ids": child_run_ids,
        "plan_ids": plan_ids,
        "plan_evidence_manifest_ids": manifest_ids,
        "verified_plan_evidence_manifest_ids": verified_manifest_ids,
        "blocked_plan_evidence_manifest_ids": blocked_manifest_ids,
        "tool_call_ids": tool_call_ids,
        "evaluation_ids": evaluation_ids,
        "artifact_ids": artifact_ids,
        "artifact_id": parent_artifact_id,
        "registered_agents": registered_agents,
        "raw_omitted": True,
        "token_omitted": True,
    }


def build_next_action_artifact(loop_id: str, args, outputs: list[dict], log_path: Path, audit_path: Path) -> dict:
    failed = [row for row in outputs if not (row.get("evaluation") or {}).get("pass")]
    last = outputs[-1] if outputs else {}
    reused = [row for row in outputs if row.get("resumed_from_existing")]
    return {
        "artifact_type": "loop_next_action",
        "loop_id": loop_id,
        "topic_hash": stable_hash(args.topic),
        "mode": args.mode,
        "rounds": args.rounds,
        "agents": args.order,
        "status": "blocked" if failed else "ready_for_codex_review",
        "recommended_next_action": redact(last.get("summary") or "No agent output available.", 500),
        "failed_evaluations": len(failed),
        "resumed_outputs": len(reused),
        "max_agent_attempts": max(int(args.max_agent_attempts or 1), 1),
        "log_path": str(log_path),
        "audit_path": str(audit_path),
        "raw_omitted": True,
        "token_omitted": True,
        "created_at": now_iso(),
    }


def run_loop(args) -> dict:
    live_agents = set()
    if args.mode in {"live-hermes", "live-both"}:
        live_agents.add("hermes")
    if args.mode in {"live-openclaw", "live-both"}:
        live_agents.add("openclaw")
    if live_agents and not args.confirm_live:
        return {
            "ok": False,
            "error": "confirm_live_required",
            "message": "Pass --confirm-live to call Hermes/OpenClaw. Dry-run remains available without confirmation.",
            "live_agents": sorted(live_agents),
            "token_omitted": True,
        }

    runtime_dir = Path(args.runtime_dir).expanduser()
    loop_id = args.loop_id or "loop_" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")
    log_path = runtime_dir / f"{loop_id}.jsonl"
    audit_path = runtime_dir / f"{loop_id}.audit.jsonl"
    artifact_path = runtime_dir / f"{loop_id}.next_action.json"
    existing_rows = read_jsonl(log_path) if args.resume else []
    for row in existing_rows:
        row["resumed_from_existing"] = True
    existing_by_key = {(row.get("round"), row.get("agent")): row for row in existing_rows}
    transcript: list[dict] = list(existing_rows)
    outputs: list[dict] = list(existing_rows)

    audit_event(audit_path, loop_id, "loop.resumed" if existing_rows else "loop.started", "loop", loop_id, {
        "mode": args.mode,
        "rounds": args.rounds,
        "agents": args.order,
        "topic_hash": stable_hash(args.topic),
        "live_agents": sorted(live_agents),
        "resume": bool(args.resume),
        "existing_outputs": len(existing_rows),
    })

    for round_no in range(1, args.rounds + 1):
        for agent in args.order:
            if args.resume and (round_no, agent) in existing_by_key:
                audit_event(audit_path, loop_id, "loop.output_reused", "loop_output", f"{agent}:{round_no}", {
                    "agent": agent,
                    "round": round_no,
                    "reason": "resume_existing_output",
                })
                continue
            prompt = loop_prompt(args.topic, round_no, transcript)
            started = now_iso()
            result = {"status": "failed", "summary": "Loop did not run.", "raw_omitted": True}
            retry_history = []
            max_attempts = max(int(args.max_agent_attempts or 1), 1)
            for attempt_no in range(1, max_attempts + 1):
                try:
                    if agent in set(args.simulate_failure_agent or []):
                        result = forced_failure_result(agent, prompt)
                    elif agent == "hermes" and "hermes" in live_agents:
                        result = call_hermes(prompt, args)
                    elif agent == "openclaw" and "openclaw" in live_agents:
                        result = call_openclaw(prompt, args)
                    else:
                        result = dry_result(agent, prompt)
                except Exception as exc:
                    result = {"status": "failed", "summary": redact(f"{type(exc).__name__}: {exc}"), "raw_omitted": True, "retryable": True}
                retry_history.append({"attempt": attempt_no, "status": result.get("status"), "summary_hash": stable_hash(result.get("summary", ""))[:16]})
                if result.get("status") in {"completed", "dry_run"} or not result.get("retryable", True):
                    break
                if attempt_no < max_attempts and args.retry_delay_sec > 0:
                    import time
                    time.sleep(args.retry_delay_sec)
            row = {
                "loop_id": loop_id,
                "round": round_no,
                "agent": agent,
                "mode": args.mode,
                "status": result["status"],
                "summary": result.get("summary", ""),
                "prompt_hash": stable_hash(prompt),
                "raw_omitted": True,
                "started_at": started,
                "ended_at": now_iso(),
                "attempt_count": len(retry_history),
                "max_attempts": max_attempts,
                "retry_history": retry_history,
            }
            if result.get("error_type"):
                row["error_type"] = result["error_type"]
            if "returncode" in result:
                row["returncode"] = result["returncode"]
            row["evaluation"] = evaluate_output(row)
            append_jsonl(log_path, row)
            audit_event(audit_path, loop_id, "loop.agent_output_recorded", "loop_output", f"{agent}:{round_no}", {
                "agent": agent,
                "round": round_no,
                "status": row["status"],
                "evaluation_score": row["evaluation"]["score"],
                "evaluation_pass": row["evaluation"]["pass"],
                "prompt_hash": row["prompt_hash"],
            })
            transcript.append(row)
            outputs.append(row)

    artifact = build_next_action_artifact(loop_id, args, outputs, log_path, audit_path)
    write_json(artifact_path, artifact)
    audit_event(audit_path, loop_id, "loop.next_action_artifact_written", "artifact", artifact_path.name, {
        "artifact_path": str(artifact_path),
        "status": artifact["status"],
        "failed_evaluations": artifact["failed_evaluations"],
    })
    audit_event(audit_path, loop_id, "loop.completed", "loop", loop_id, {
        "ok": all(row["status"] in {"completed", "dry_run"} and row["evaluation"]["pass"] for row in outputs),
        "outputs": len(outputs),
        "artifact_path": str(artifact_path),
    })
    mis_ledger = {"enabled": False, "ok": None}
    if args.mis_ledger:
        try:
            mis_ledger = record_loop_to_mis(args, loop_id, outputs, artifact)
        except Exception as exc:
            mis_ledger = {
                "enabled": True,
                "ok": False,
                "error": redact(f"{type(exc).__name__}: {exc}", 600),
                "raw_omitted": True,
                "token_omitted": True,
            }

    return {
        "ok": all(row["status"] in {"completed", "dry_run"} and row["evaluation"]["pass"] for row in outputs) and (not args.mis_ledger or bool(mis_ledger.get("ok"))),
        "loop_id": loop_id,
        "mode": args.mode,
        "rounds": args.rounds,
        "agents": args.order,
        "log_path": str(log_path),
        "audit_path": str(audit_path),
        "next_action_artifact_path": str(artifact_path),
        "next_action_artifact": artifact,
        "runtime_dir_gitignored": all(git_check_ignored(path) for path in [log_path, audit_path, artifact_path]),
        "mis_ledger": mis_ledger,
        "outputs": outputs,
        "token_omitted": True,
        "raw_omitted": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a supervised Hermes/OpenClaw collaboration loop.")
    parser.add_argument("--topic", required=True, help="Loop objective. Keep it about coordination, not secrets.")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--mode", choices=["dry-run", "live-hermes", "live-openclaw", "live-both"], default="dry-run")
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--loop-id", default="")
    parser.add_argument("--runtime-dir", default=str(DEFAULT_RUNTIME_DIR))
    parser.add_argument("--resume", action="store_true", help="Reuse existing loop JSONL rows for the same --loop-id and continue missing iterations.")
    parser.add_argument("--order", nargs="+", choices=["hermes", "openclaw"], default=["hermes", "openclaw"])
    parser.add_argument("--hermes-url", default=os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:8642"))
    parser.add_argument("--hermes-model", default=os.environ.get("HERMES_LOOP_MODEL", "hermes-agent"))
    parser.add_argument("--hermes-timeout", type=int, default=25)
    parser.add_argument("--max-tokens", type=int, default=220)
    parser.add_argument("--openclaw-bin", default=os.environ.get("OPENCLAW_BIN", "/opt/homebrew/bin/openclaw"))
    parser.add_argument("--openclaw-agent", default=os.environ.get("OPENCLAW_AGENT", "main"))
    parser.add_argument("--openclaw-timeout", type=int, default=120)
    parser.add_argument("--max-agent-attempts", type=int, default=1)
    parser.add_argument("--retry-delay-sec", type=float, default=1.0)
    parser.add_argument("--simulate-failure-agent", action="append", choices=["hermes", "openclaw"], default=[], help="Smoke-test hook: force an agent lane to fail without calling live runtimes.")
    parser.add_argument("--mis-ledger", action="store_true", help="Record loop tasks/runs/tool calls/evaluations/audit/artifact through Agent Gateway.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", DEFAULT_WORKSPACE_ID))
    parser.add_argument("--api-key", default=os.environ.get("AGENTOPS_API_KEY", ""))
    parser.add_argument("--request-timeout", type=int, default=int(os.environ.get("AGENTOPS_REQUEST_TIMEOUT", "30")))
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.rounds < 1 or args.rounds > 8:
        parser.error("--rounds must be between 1 and 8")
    result = run_loop(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
