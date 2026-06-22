#!/usr/bin/env python3
"""Verify a Next-created Agent Gateway task is completed by the worker CLI."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "nextjs_agent_gateway_cli_worker_dogfood_v1"
SMOKE_API_KEY = "nextjs_cli_worker_dogfood_required_api_key"

sys.path.insert(0, str(SCRIPTS))

from nextjs_playwright_snapshot_smoke import (  # noqa: E402
    free_port,
    leaked_secret,
    require,
    restore_next_env,
    run,
    start_process,
    wait_http,
)


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def http_json_status(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    *,
    token: str | None = None,
    timeout: int = 60,
) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}


def create_token(api_base: str, *, agent_id: str, workspace_id: str) -> tuple[str, str]:
    scopes = [
        "agents:write",
        "agents:heartbeat",
        "agent_plans:write",
        "plan_evidence:read",
        "plan_evidence:write",
        "tasks:create",
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
    status, payload = http_json_status(
        "POST",
        f"{api_base}/api/agent-gateway/enrollment/create",
        {
            "agent_id": agent_id,
            "workspace_id": workspace_id,
            "name": f"Next CLI worker dogfood {agent_id}",
            "role": "Next-created task worker",
            "runtime_type": "mock",
            "scopes": scopes,
            "ttl_days": 1,
            "heartbeat_timeout_sec": 60,
        },
    )
    require(status == 201, f"token create failed: {status} {payload}")
    token_id = str(payload.get("token_id") or "")
    token = str(payload.get("token") or "")
    require(token_id and token, f"token payload missing token material: {payload}")
    return token_id, token


def revoke_token(api_base: str, token_id: str) -> None:
    if token_id:
        http_json_status("POST", f"{api_base}/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


def gateway_task_body(task_id: str, *, owner_agent_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "title": "Next proxy creates task for CLI worker dogfood",
        "description": "Next.js /api/mis creates a scoped Agent Gateway task that a real worker CLI process must claim and complete.",
        "owner_agent_id": owner_agent_id,
        "status": "planned",
        "priority": "high",
        "risk_level": "low",
        "acceptance_criteria": "CLI worker must write run, tool, evaluation, audit, artifact, memory and verified plan-evidence records.",
        "budget_limit_usd": 1.0,
    }


def run_worker_cli(api_base: str, token: str, agent_id: str, workspace_id: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = api_base
    env["AGENTOPS_WORKSPACE_ID"] = workspace_id
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "agent_worker.py"),
            "--once",
            "--adapter",
            "mock",
            "--agent-id",
            agent_id,
            "--base-url",
            api_base,
            "--api-key",
            token,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=260,
        check=False,
    )
    require(proc.returncode == 0, f"worker CLI failed: {proc.stderr or proc.stdout}")
    require(not leaked_secret(proc.stdout + proc.stderr), "worker CLI leaked token-like material")
    payload = json.loads(proc.stdout or "{}")
    require(payload.get("processed") == 1, f"worker did not process exactly one task: {payload}")
    return payload


def first_worker_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = ((payload.get("results") or [{}])[0] or {})
    require(isinstance(result, dict), f"worker result malformed: {payload}")
    return result


def main() -> int:
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "error": "npx is required for Next.js CLI worker dogfood smoke"}, indent=2), file=sys.stderr)
        return 1

    suffix = stamp()
    workspace_id = f"ws_next_cli_worker_{suffix}"
    agent_id = f"agt_next_cli_worker_{suffix}"
    task_id = f"tsk_next_cli_worker_{suffix}"
    token_id = ""
    token = ""
    processes: list[subprocess.Popen[str]] = []
    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"
    transcripts: list[Any] = []

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-cli-worker-dogfood-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            reset_env = os.environ.copy()
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset_env["AGENTOPS_API_KEY"] = SMOKE_API_KEY
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = os.environ.copy()
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_env["AGENTOPS_API_KEY"] = SMOKE_API_KEY
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/api/mis/dashboard/metrics")

            token_id, token = create_token(api_base, agent_id=agent_id, workspace_id=workspace_id)
            create_status, create_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/agent-gateway/tasks",
                gateway_task_body(task_id, owner_agent_id=agent_id),
                token=token,
            )
            require(create_status == 201, f"Next task create failed: {create_status} {create_payload}")
            require(create_payload.get("token_omitted") is True, f"Next create payload should omit token: {create_payload}")
            transcripts.append(create_payload)

            worker_payload = run_worker_cli(api_base, token, agent_id, workspace_id)
            worker_result = first_worker_result(worker_payload)
            run_id = str(worker_result.get("run_id") or "")
            manifest_id = str(worker_result.get("plan_evidence_manifest_id") or "")
            require(run_id and manifest_id, f"worker missing run or manifest id: {worker_payload}")
            require(worker_result.get("plan_evidence_pass") is True, f"worker plan evidence failed: {worker_result}")

            next_task_status, next_task_payload = http_json_status(
                "GET",
                f"{next_base}/api/mis/agent-gateway/tasks/{task_id}",
                token=token,
            )
            next_run_status, next_run_payload = http_json_status(
                "GET",
                f"{next_base}/api/mis/runs/{run_id}?workspace_id={workspace_id}",
            )
            next_manifest_status, next_manifest_payload = http_json_status(
                "GET",
                f"{next_base}/api/mis/agent-gateway/plan-evidence-manifests/{manifest_id}/verify",
                token=token,
            )
            transcripts.extend([next_task_payload, next_run_payload, next_manifest_payload, worker_payload])

            task = next_task_payload.get("task") or next_task_payload
            run_detail = next_run_payload.get("run") or {}
            require(next_task_status == 200, f"Next Gateway task readback failed: {next_task_status} {next_task_payload}")
            require(task.get("status") == "completed", f"Next-created task was not completed by CLI worker: {next_task_payload}")
            require(next_run_status == 200, f"Next run readback failed: {next_run_status} {next_run_payload}")
            require(run_detail.get("status") == "completed", f"run not completed: {next_run_payload}")
            require(len(next_run_payload.get("tool_calls") or []) >= 1, f"run missing tool calls: {next_run_payload}")
            require(any(item.get("pass_fail") == "pass" for item in next_run_payload.get("evaluations") or []), f"run missing passing evaluation: {next_run_payload}")
            require(next_manifest_status == 200, f"Next plan-evidence verify failed: {next_manifest_status} {next_manifest_payload}")
            manifest_verification = next_manifest_payload.get("verification") or {}
            require(manifest_verification.get("pass") is True, f"plan-evidence did not verify through Next proxy: {next_manifest_payload}")

            transcript_text = json.dumps(transcripts, ensure_ascii=False, sort_keys=True)
            require(not leaked_secret(transcript_text), "Next/CLI worker dogfood leaked token-like material")
            require(token not in transcript_text, "Next/CLI worker dogfood leaked the raw Gateway token")

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "workspace_id": workspace_id,
                "agent_id": agent_id,
                "task_id": task_id,
                "run_id": run_id,
                "plan_evidence_manifest_id": manifest_id,
                "proxy_route": "/api/mis/agent-gateway/tasks",
                "worker_entrypoint": "scripts/agent_worker.py --once --adapter mock",
                "evidence_readback": "/api/mis/runs/:run_id and /api/mis/agent-gateway/plan-evidence-manifests/:id/verify",
                "next_task_status": task.get("status"),
                "run_status": run_detail.get("status"),
                "tool_calls": len(next_run_payload.get("tool_calls") or []),
                "evaluations": len(next_run_payload.get("evaluations") or []),
                "plan_evidence_pass": manifest_verification.get("pass"),
                "secret_leaked": False,
                "token_omitted": True,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        if token_id:
            try:
                revoke_token(api_base, token_id)
            except Exception:
                pass
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        run(["bash", "-lc", f"lsof -tiTCP:{next_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["bash", "-lc", f"lsof -tiTCP:{api_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["rm", "-rf", str(NEXT_APP / ".next")], timeout=10)
        restore_next_env()


if __name__ == "__main__":
    raise SystemExit(main())
