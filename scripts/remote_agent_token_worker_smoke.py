#!/usr/bin/env python3
"""
Smoke-test the remote Agent Gateway enrollment path with a real worker loop.

The token is kept in memory, omitted from output, and revoked by default.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentops_mis_cli.codex_runtime import DEFAULT_CODEX_APP_BIN, codex_preflight, resolve_codex_binary


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
    parser.add_argument("--adapter", choices=["mock", "hermes", "openclaw", "codex"], default="mock")
    parser.add_argument("--confirm-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--codex-bin", default=os.environ.get("CODEX_BIN", ""))
    parser.add_argument("--evidence-class", choices=["auto", "real_runtime", "deterministic_fixture"], default="auto")
    parser.add_argument("--keep-token", action="store_true", help="Do not revoke the generated token after the smoke.")
    return parser


def runtime_attestation(args) -> dict:
    if args.adapter == "codex":
        binary = resolve_codex_binary(args.codex_bin)
        expected = Path(DEFAULT_CODEX_APP_BIN)
        official_bundle = False
        try:
            official_bundle = binary.resolve() == expected.resolve() and expected.is_file()
        except OSError:
            official_bundle = False
        preflight = codex_preflight(binary_path=str(binary), cwd=ROOT, timeout=10)
        return {
            "attested": bool(official_bundle and preflight.get("ok")),
            "adapter": "codex",
            "official_chatgpt_bundle": official_bundle,
            "version_ok": preflight.get("version_ok") is True,
            "version_summary": preflight.get("version_summary"),
            "token_omitted": True,
        }
    return {
        "attested": bool(args.adapter in {"hermes", "openclaw"} and args.confirm_run),
        "adapter": args.adapter,
        "local_adapter_contract": args.adapter in {"hermes", "openclaw"},
        "token_omitted": True,
    }


def main() -> int:
    args = build_parser().parse_args()
    stamp = now_stamp()
    agent_id = args.agent_id or f"agt_remote_worker_smoke_{stamp}"
    task_id = f"tsk_remote_worker_smoke_{stamp}"
    token_id = None
    token = None
    exit_code = 1
    result: dict = {
        "ok": False,
        "agent_id": agent_id,
        "task_id": task_id,
        "adapter": args.adapter,
        "token_omitted": True,
    }
    try:
        attestation = runtime_attestation(args)
        if args.evidence_class == "real_runtime" and attestation.get("attested") is not True:
            raise RuntimeError("real_runtime evidence requires an attested local runtime; arbitrary Codex binaries are fixture-only")
        evidence_class = (
            "real_runtime"
            if attestation.get("attested") is True and args.evidence_class in {"auto", "real_runtime"}
            else "deterministic_fixture"
        )
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
            "runtime_events:write",
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
        launch_steps = created.get("next_steps") or {}
        launch_text = json.dumps(launch_steps, ensure_ascii=False)
        if launch_steps.get("adapter") != args.adapter or f"--adapter {args.adapter}" not in launch_text:
            raise RuntimeError(f"enrollment launch steps did not preserve adapter {args.adapter}")
        launch_safety = (launch_steps.get("method_gate_contract") or {}).get("safety") or {}
        if args.adapter == "codex" and ("--confirm-run" not in launch_text or launch_safety.get("read_only_worker") is not True):
            raise RuntimeError("Codex launch steps must require confirmation and preserve the read-only contract")

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
            "--use-session",
            "--session-ttl-sec",
            "900",
        ]
        if args.confirm_run:
            cmd.append("--confirm-run")
        if args.codex_bin:
            cmd.extend(["--codex-bin", args.codex_bin])
        worker_env = os.environ.copy()
        worker_env["AGENTOPS_API_KEY"] = token
        worker_env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
        worker_env["AGENTOPS_AGENT_ID"] = agent_id
        proc = subprocess.run(cmd, cwd=ROOT, env=worker_env, capture_output=True, text=True, timeout=max(args.timeout, 60), check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"worker failed: {proc.stderr or proc.stdout}")
        worker_result = json.loads(proc.stdout or "{}")
        run_id = ((worker_result.get("results") or [{}])[0] or {}).get("run_id")
        if not run_id:
            raise RuntimeError(f"worker did not return run_id: {worker_result}")
        worker_item = ((worker_result.get("results") or [{}])[0] or {})

        status, run_detail = http_json("GET", args.base_url, f"/api/agent-gateway/runs/{run_id}", token=token)
        if status != 200:
            raise RuntimeError(f"run detail failed: {status} {run_detail}")
        run = run_detail.get("run") or {}
        tool_calls = run_detail.get("tool_calls") or []
        evaluations = run_detail.get("evaluations") or []
        runtime_events = run_detail.get("runtime_events") or []
        artifacts = run_detail.get("artifacts") or []
        audit_logs = run_detail.get("audit_logs") or []
        memories = run_detail.get("memories") or []
        record_receipts = worker_item.get("record_receipts") or {}
        audit_id = record_receipts.get("audit_id")
        memory_id = record_receipts.get("memory_candidate_id")
        audit_readback = any(item.get("audit_id") == audit_id for item in audit_logs)
        memory_readback = any(item.get("memory_id") == memory_id for item in memories)
        status, agent_detail = http_json("GET", args.base_url, f"/api/agents/{agent_id}")
        registered_agent = agent_detail.get("agent") if status == 200 and isinstance(agent_detail, dict) else {}
        session = worker_result.get("session") or {}
        ok = (
            run.get("status") == "completed"
            and any(item.get("tool_name") == f"agent_worker.{args.adapter}" and item.get("status") == "completed" for item in tool_calls)
            and any(item.get("pass_fail") == "pass" for item in evaluations)
            and bool(worker_item.get("plan_id"))
            and bool(worker_item.get("plan_evidence_manifest_id"))
            and worker_item.get("plan_evidence_pass") is True
            and bool(session.get("session_id"))
            and session.get("token_omitted") is True
            and bool(runtime_events)
            and bool(artifacts)
            and record_receipts.get("audit_recorded") is True
            and record_receipts.get("memory_candidate_recorded") is True
            and record_receipts.get("token_omitted") is True
            and audit_readback
            and memory_readback
            and registered_agent.get("runtime_type") == args.adapter
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
            "runtime_events": len(runtime_events),
            "artifacts": len(artifacts),
            "audit_logs": len(audit_logs),
            "memories": len(memories),
            "record_receipts_verified": bool(
                record_receipts.get("audit_recorded") is True
                and record_receipts.get("memory_candidate_recorded") is True
                and audit_readback
                and memory_readback
            ),
            "agent_runtime_type_verified": registered_agent.get("runtime_type") == args.adapter,
            "launch_adapter_verified": True,
            "short_lived_session_used": bool(session.get("session_id")),
            "worker_processed": worker_result.get("processed"),
            "live_execution_performed": bool(args.adapter != "mock" and args.confirm_run),
            "real_runtime_execution_performed": bool(evidence_class == "real_runtime" and args.adapter != "mock" and args.confirm_run),
            "evidence_class": evidence_class,
            "runtime_attestation": attestation,
            "product_readiness_proof": bool(evidence_class == "real_runtime" and attestation.get("attested") is True and args.adapter != "mock" and args.confirm_run and ok),
        })
        exit_code = 0 if ok else 1
    except Exception as exc:
        result["error"] = str(exc)
        exit_code = 1
    finally:
        if token_id and not args.keep_token:
            status, revoked = http_json("POST", args.base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})
            result["revocation"] = {"status": status, "revoked": revoked.get("revoked") if isinstance(revoked, dict) else None}
            if status != 200 or not isinstance(revoked, dict) or int(revoked.get("revoked") or 0) < 1:
                result["ok"] = False
                result["product_readiness_proof"] = False
                result["revocation_verified"] = False
                exit_code = 1
            else:
                result["revocation_verified"] = True
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
