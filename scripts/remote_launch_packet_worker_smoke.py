#!/usr/bin/env python3
"""Verify the enrollment launch packet can actually run a remote worker."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return exc.code, body


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def launch_text(steps: dict) -> str:
    return json.dumps(steps, ensure_ascii=False, sort_keys=True)


def smoke(base_url: str, stamp: str) -> dict:
    agent_id = f"agt_launch_packet_worker_{stamp}"
    task_id = f"tsk_launch_packet_worker_{stamp}"
    token_id = None
    token = None
    try:
        create_status, created = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
            "agent_id": agent_id,
            "name": "Launch Packet Worker Smoke",
            "runtime_type": "mock",
            "workspace_id": "local-demo",
            "base_url": base_url,
            "scopes": [
                "agents:write",
                "agents:heartbeat",
                "knowledge:read",
                "agent_plans:read",
                "agent_plans:write",
                "plan_evidence:read",
                "plan_evidence:write",
                "tasks:create",
                "tasks:read",
                "tasks:claim",
                "runs:write",
                "toolcalls:write",
                "artifacts:write",
                "memories:propose",
                "evaluations:submit",
                "audit:write",
            ],
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        })
        require(create_status == 201, f"enrollment create failed: {create_status} {created}")
        token = created.get("token")
        token_id = created.get("token_id")
        steps = created.get("next_steps") or {}
        require(token and token_id, "create response missing one-time token")
        text = launch_text(steps)
        require(token not in text, "raw token leaked into launch packet")
        require(steps.get("adapter") == "mock", f"launch packet adapter mismatch: {steps}")
        require("agentops status" in text and "agentops-worker" in text, f"launch packet missing product commands: {steps}")
        require("agentops-worker preflight" in text, f"launch packet missing adapter preflight command: {steps}")
        require("service-template --manager launchd" in text and "service-template --manager systemd" in text, f"launch packet missing service template commands: {steps}")
        require("service-install --manager launchd" in text and "service-install --manager systemd" in text, f"launch packet missing service install commands: {steps}")
        require("service-check --manager launchd" in text and "service-check --manager systemd" in text, f"launch packet missing service check commands: {steps}")
        require("scripts/agent_worker.py" in text, f"launch packet missing repo fallback commands: {steps}")
        require("agentops session create" in text and "--use-session" in text, f"launch packet missing short-lived session path: {steps}")

        status_status, status_payload = http_json("GET", base_url, "/api/agent-gateway/status", token=token)
        require(status_status == 200, f"token status failed: {status_status} {status_payload}")
        require(status_payload.get("auth", {}).get("agent_id") == agent_id, f"status agent mismatch: {status_payload}")

        task_status, task = http_json("POST", base_url, "/api/tasks", {
            "task_id": task_id,
            "workspace_id": "local-demo",
            "title": "launch packet worker smoke task",
            "description": "Verify a remote worker can run from the enrollment launch packet environment.",
            "owner_agent_id": agent_id,
            "status": "planned",
            "priority": "high",
            "risk_level": "low",
            "acceptance_criteria": "Worker must write run/tool/eval/audit evidence and complete the task.",
        })
        require(task_status == 201, f"task create failed: {task_status} {task}")

        env = os.environ.copy()
        env.update({
            "AGENTOPS_BASE_URL": steps.get("base_url") or base_url,
            "AGENTOPS_WORKSPACE_ID": steps.get("workspace_id") or "local-demo",
            "AGENTOPS_AGENT_ID": steps.get("agent_id") or agent_id,
            "AGENTOPS_API_KEY": token,
        })
        cmd = [
            sys.executable,
            "-m",
            "agentops_mis_cli.worker",
            "--once",
            "--adapter",
            steps.get("adapter") or "mock",
            "--use-session",
            "--session-ttl-sec",
            "900",
        ]
        proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180, check=False)
        require(proc.returncode == 0, f"worker failed: {proc.stderr or proc.stdout}")
        require(token not in proc.stdout and token not in proc.stderr, "worker output leaked raw token")
        worker_result = json.loads(proc.stdout or "{}")
        result = (worker_result.get("results") or [{}])[0]
        session = worker_result.get("session") or {}
        run_id = result.get("run_id")
        require(run_id, f"worker did not return run_id: {worker_result}")
        require(session.get("session_id"), f"worker did not mint a session: {worker_result}")

        detail_status, detail = http_json("GET", base_url, f"/api/runs/{run_id}")
        require(detail_status == 200, f"run detail failed: {detail_status} {detail}")
        run = detail.get("run") or {}
        tool_calls = detail.get("tool_calls") or []
        evaluations = detail.get("evaluations") or []
        ok = (
            run.get("status") == "completed"
            and any(item.get("tool_name") == "agent_worker.mock" and item.get("status") == "completed" for item in tool_calls)
            and any(item.get("pass_fail") == "pass" for item in evaluations)
        )
        require(ok, f"ledger evidence incomplete: {detail}")
        return {
            "agent_id": agent_id,
            "task_id": task_id,
            "run_id": run_id,
            "token_id": token_id,
            "adapter": steps.get("adapter"),
            "status_mode": status_payload.get("auth", {}).get("mode"),
            "session_id": session.get("session_id"),
            "tool_calls": len(tool_calls),
            "evaluations": len(evaluations),
            "token_omitted": True,
        }
    finally:
        if token_id:
            http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a remote worker using the enrollment launch packet.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args(argv)
    result = {"ok": True, "base_url": args.base_url, "smoke": smoke(args.base_url, now_stamp())}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise
