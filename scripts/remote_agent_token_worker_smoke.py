#!/usr/bin/env python3
"""
Smoke-test the remote Agent Gateway enrollment path with a real worker loop.

The token is kept in memory, omitted from output, and revoked by default.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, token: str | None = None, timeout: int = 60):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return exc.code, body
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run remote-token worker smoke against local AgentOps MIS.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--agent-id", default=None)
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw"], default="mock")
    parser.add_argument("--confirm-run", action="store_true")
    parser.add_argument("--keep-token", action="store_true", help="Do not revoke the generated token after the smoke.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    stamp = now_stamp()
    agent_id = args.agent_id or f"agt_remote_worker_smoke_{stamp}"
    task_id = f"tsk_remote_worker_smoke_{stamp}"
    token_id = None
    token = None
    result: dict = {
        "ok": False,
        "agent_id": agent_id,
        "task_id": task_id,
        "adapter": args.adapter,
        "token_omitted": True,
    }
    try:
        scopes = [
            "agents:write",
            "agents:heartbeat",
            "knowledge:read",
            "knowledge:write",
            "agent_plans:read",
            "agent_plans:write",
            "plan_evidence:read",
            "plan_evidence:write",
            "tasks:read",
            "tasks:claim",
            "runs:write",
            "toolcalls:write",
            "artifacts:write",
            "approvals:request",
            "memories:propose",
            "evaluations:submit",
            "audit:write",
        ]
        status, created = http_json("POST", args.base_url, "/api/agent-gateway/enrollment/create", {
            "agent_id": agent_id,
            "name": "Remote Worker Smoke",
            "role": "Remote Worker Smoke",
            "runtime_type": args.adapter,
            "workspace_id": "local-demo",
            "scopes": scopes,
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        })
        if status != 201:
            raise RuntimeError(f"enrollment create failed: {status} {created}")
        token = created["token"]
        token_id = created["token_id"]
        result["token_id"] = token_id

        status, task = http_json("POST", args.base_url, "/api/tasks", {
            "task_id": task_id,
            "title": "remote token worker smoke task",
            "description": "Verify scoped Agent Gateway token can drive a worker loop without storing the raw token.",
            "owner_agent_id": agent_id,
            "status": "planned",
            "priority": "high",
            "risk_level": "low",
            "acceptance_criteria": "Worker must write run/tool/eval/audit evidence and complete the task.",
        })
        if status != 201:
            raise RuntimeError(f"task create failed: {status} {task}")

        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "agent_worker.py"),
            "--once",
            "--adapter",
            args.adapter,
            "--agent-id",
            agent_id,
            "--task-id",
            task_id,
            "--no-enforce-intake",
            "--base-url",
            args.base_url,
            "--api-key",
            token,
        ]
        if args.confirm_run:
            cmd.append("--confirm-run")
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=260, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"worker failed: {proc.stderr or proc.stdout}")
        worker_result = json.loads(proc.stdout or "{}")
        run_id = ((worker_result.get("results") or [{}])[0] or {}).get("run_id")
        if not run_id:
            raise RuntimeError(f"worker did not return run_id: {worker_result}")
        worker_item = ((worker_result.get("results") or [{}])[0] or {})

        status, run_detail = http_json("GET", args.base_url, f"/api/runs/{run_id}")
        if status != 200:
            raise RuntimeError(f"run detail failed: {status} {run_detail}")
        run = run_detail.get("run") or {}
        tool_calls = run_detail.get("tool_calls") or []
        evaluations = run_detail.get("evaluations") or []
        ok = (
            run.get("status") == "completed"
            and any(item.get("tool_name") == f"agent_worker.{args.adapter}" and item.get("status") == "completed" for item in tool_calls)
            and any(item.get("pass_fail") == "pass" for item in evaluations)
            and bool(worker_item.get("plan_id"))
            and bool(worker_item.get("plan_evidence_manifest_id"))
            and worker_item.get("plan_evidence_pass") is True
        )
        result.update({
            "ok": ok,
            "run_id": run_id,
            "plan_id": worker_item.get("plan_id"),
            "plan_evidence_manifest_id": worker_item.get("plan_evidence_manifest_id"),
            "plan_evidence_status": worker_item.get("plan_evidence_status"),
            "plan_evidence_pass": worker_item.get("plan_evidence_pass"),
            "run_status": run.get("status"),
            "tool_calls": len(tool_calls),
            "evaluations": len(evaluations),
            "worker_processed": worker_result.get("processed"),
        })
        return 0 if ok else 1
    except Exception as exc:
        result["error"] = str(exc)
        return 1
    finally:
        if token_id and not args.keep_token:
            status, revoked = http_json("POST", args.base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})
            result["revocation"] = {"status": status, "revoked": revoked.get("revoked") if isinstance(revoked, dict) else None}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
