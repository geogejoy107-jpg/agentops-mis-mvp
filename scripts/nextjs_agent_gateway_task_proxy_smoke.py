#!/usr/bin/env python3
"""Verify the Next.js MIS proxy preserves Agent Gateway task-create semantics."""
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
CONTRACT_ID = "nextjs_agent_gateway_task_proxy_v1"
SMOKE_API_KEY = "nextjs_gateway_proxy_required_api_key"

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
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = dict(extra_headers or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}


def create_token(api_base: str, *, agent_id: str, workspace_id: str, scopes: list[str]) -> tuple[str, str]:
    status, payload = http_json_status(
        "POST",
        f"{api_base}/api/agent-gateway/enrollment/create",
        {
            "agent_id": agent_id,
            "workspace_id": workspace_id,
            "name": f"Next proxy smoke {agent_id}",
            "role": "Next Agent Gateway proxy smoke",
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
    if not token_id:
        return
    http_json_status("POST", f"{api_base}/api/agent-gateway/enrollment/revoke", {"token_id": token_id})


def gateway_task_body(task_id: str, *, owner_agent_id: str, workspace_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "task_id": task_id,
        "title": "Next proxy scoped Agent Gateway task",
        "description": "Created through the Next.js /api/mis proxy.",
        "owner_agent_id": owner_agent_id,
        "status": "planned",
        "priority": "high",
        "risk_level": "low",
        "acceptance_criteria": "Next proxy preserves token, workspace, and owner binding.",
        "budget_limit_usd": 1.0,
    }
    if workspace_id is not None:
        body["workspace_id"] = workspace_id
    return body


def gateway_plan_body(plan_id: str, task_id: str) -> dict[str, Any]:
    return {
        "plan_id": plan_id,
        "task_id": task_id,
        "task_understanding": "Execute through the scoped Next proxy and close bounded ledger evidence.",
        "referenced_specs": ["PROJECT_SPEC.md", "AGENT_WORKFLOW.md", "docs/AGENT_WORK_METHOD_BLOCK.md"],
        "referenced_memories": ["knowledge/shared/common_failures.md"],
        "referenced_bases": ["base_local_tasks", "base_local_memory"],
        "proposed_files_to_change": ["scripts/nextjs_agent_gateway_task_proxy_smoke.py"],
        "risk_level": "medium",
        "execution_steps": ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"],
        "verification_plan": "Verify scoped plan, run, tool, evaluation, artifact, audit, and manifest readback.",
        "rollback_plan": "Switch the Next route back to direct Postgres after preserving immutable evidence.",
        "status": "submitted",
    }


def normalize_task(payload: dict[str, Any]) -> dict[str, Any]:
    task = payload.get("task") if isinstance(payload.get("task"), dict) else payload
    return {
        "task_id": task.get("task_id"),
        "workspace_id": task.get("workspace_id"),
        "owner_agent_id": task.get("owner_agent_id"),
        "status": task.get("status"),
        "priority": task.get("priority"),
        "risk_level": task.get("risk_level"),
    }


def main() -> int:
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "error": "npx is required for Next.js proxy smoke"}, indent=2), file=sys.stderr)
        return 1

    suffix = stamp()
    workspace_id = f"ws_next_gateway_proxy_{suffix}"
    agent_id = f"agt_next_gateway_proxy_{suffix}"
    observer_agent_id = f"{agent_id}_observer"
    other_agent_id = f"{agent_id}_other"
    task_id = f"tsk_next_gateway_proxy_{suffix}"
    token_ids: list[str] = []
    raw_tokens: list[str] = []
    transcripts: list[dict[str, Any]] = []
    processes: list[subprocess.Popen[str]] = []
    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-gateway-proxy-") as tmp:
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
            next_env["AGENTOPS_TS_CONTROL_PLANE_MODE"] = "proxy"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/api/mis/dashboard/metrics")

            allowed_token_id, allowed_token = create_token(
                api_base,
                agent_id=agent_id,
                workspace_id=workspace_id,
                scopes=["agents:heartbeat", "tasks:create", "tasks:read", "runs:write", "toolcalls:write", "evaluations:submit", "artifacts:write", "agent_plans:write", "plan_evidence:write", "audit:write"],
            )
            token_ids.append(allowed_token_id)
            raw_tokens.append(allowed_token)
            observer_token_id, observer_token = create_token(
                api_base,
                agent_id=observer_agent_id,
                workspace_id=workspace_id,
                scopes=["agents:heartbeat", "tasks:read", "audit:write"],
            )
            token_ids.append(observer_token_id)
            raw_tokens.append(observer_token)

            proxy_task_url = f"{next_base}/api/mis/agent-gateway/tasks"
            no_token_status, no_token_payload = http_json_status(
                "POST",
                proxy_task_url,
                gateway_task_body(f"{task_id}_no_token", owner_agent_id=agent_id),
            )
            missing_scope_status, missing_scope_payload = http_json_status(
                "POST",
                proxy_task_url,
                gateway_task_body(f"{task_id}_missing_scope", owner_agent_id=observer_agent_id),
                token=observer_token,
            )
            body_workspace_status, body_workspace_payload = http_json_status(
                "POST",
                proxy_task_url,
                gateway_task_body(f"{task_id}_body_workspace", owner_agent_id=agent_id, workspace_id="other-workspace"),
                token=allowed_token,
            )
            header_workspace_status, header_workspace_payload = http_json_status(
                "POST",
                proxy_task_url,
                gateway_task_body(f"{task_id}_header_workspace", owner_agent_id=agent_id),
                token=allowed_token,
                extra_headers={"X-AgentOps-Workspace-Id": "other-workspace"},
            )
            other_agent_status, other_agent_payload = http_json_status(
                "POST",
                proxy_task_url,
                gateway_task_body(f"{task_id}_other_agent", owner_agent_id=other_agent_id),
                token=allowed_token,
            )
            create_status, create_payload = http_json_status(
                "POST",
                proxy_task_url,
                gateway_task_body(task_id, owner_agent_id=agent_id),
                token=allowed_token,
            )
            plan_id = f"plan_{suffix}"
            proxy_plan_url = f"{next_base}/api/mis/agent-gateway/agent-plans"
            plan_body = gateway_plan_body(plan_id, task_id)
            plan_no_token_status, plan_no_token_payload = http_json_status(
                "POST", proxy_plan_url, plan_body
            )
            plan_missing_scope_status, plan_missing_scope_payload = http_json_status(
                "POST", proxy_plan_url, plan_body, token=observer_token
            )
            plan_status, plan_payload = http_json_status(
                "POST", proxy_plan_url, plan_body, token=allowed_token
            )
            next_get_status, next_get_payload = http_json_status(
                "GET",
                f"{next_base}/api/mis/agent-gateway/tasks/{task_id}",
                token=allowed_token,
            )
            direct_get_status, direct_get_payload = http_json_status(
                "GET",
                f"{api_base}/api/tasks/{task_id}?workspace_id={workspace_id}",
            )
            next_task_get_status, next_task_get_payload = http_json_status(
                "GET",
                f"{next_base}/api/mis/tasks/{task_id}?workspace_id={workspace_id}",
            )
            proxy_run_url = f"{next_base}/api/mis/agent-gateway/runs/start"
            run_body = {
                "task_id": task_id,
                "agent_plan_id": plan_id,
                "runtime_type": "openclaw",
                "input_summary": "Next proxy run start proof.",
            }
            run_no_token_status, run_no_token_payload = http_json_status("POST", proxy_run_url, run_body)
            run_missing_scope_status, run_missing_scope_payload = http_json_status(
                "POST",
                proxy_run_url,
                run_body,
                token=observer_token,
            )
            run_start_status, run_start_payload = http_json_status(
                "POST",
                proxy_run_url,
                run_body,
                token=allowed_token,
            )
            proxied_run_id = str((run_start_payload.get("run") or {}).get("run_id") or "")
            proxy_heartbeat_url = f"{next_base}/api/mis/agent-gateway/runs/{proxied_run_id}/heartbeat"
            heartbeat_body = {
                "task_id": task_id,
                "status": "running",
                "duration_ms": 1234,
                "output_tokens": 11,
                "output_summary": "Next proxy run heartbeat proof.",
            }
            heartbeat_no_token_status, heartbeat_no_token_payload = http_json_status(
                "POST", proxy_heartbeat_url, heartbeat_body
            )
            heartbeat_missing_scope_status, heartbeat_missing_scope_payload = http_json_status(
                "POST", proxy_heartbeat_url, heartbeat_body, token=observer_token
            )
            heartbeat_status, heartbeat_payload = http_json_status(
                "POST", proxy_heartbeat_url, heartbeat_body, token=allowed_token
            )
            completion_status, completion_payload = http_json_status(
                "POST",
                proxy_heartbeat_url,
                {**heartbeat_body, "status": "completed", "output_summary": "Next proxy run completion proof."},
                token=allowed_token,
            )
            revival_status, revival_payload = http_json_status(
                "POST",
                proxy_heartbeat_url,
                {"task_id": task_id, "status": "running"},
                token=allowed_token,
            )
            proxy_tool_url = f"{next_base}/api/mis/agent-gateway/tool-calls"
            proxy_evaluation_url = f"{next_base}/api/mis/agent-gateway/evaluations/submit"
            proxy_artifact_url = f"{next_base}/api/mis/agent-gateway/artifacts"
            tool_call_id = f"tc_{suffix}"
            evaluation_id = f"eval_{suffix}"
            artifact_id = f"art_{suffix}"
            tool_body = {
                "tool_call_id": tool_call_id,
                "run_id": proxied_run_id,
                "tool_name": "agent_gateway.note",
                "tool_category": "custom",
                "risk_level": "low",
                "status": "completed",
                "args": {"raw_omitted": True},
                "result_summary": "Next proxy tool evidence proof.",
            }
            tool_no_token_status, tool_no_token_payload = http_json_status("POST", proxy_tool_url, tool_body)
            tool_missing_scope_status, tool_missing_scope_payload = http_json_status(
                "POST", proxy_tool_url, tool_body, token=observer_token
            )
            tool_status, tool_payload = http_json_status("POST", proxy_tool_url, tool_body, token=allowed_token)
            evaluation_status, evaluation_payload = http_json_status(
                "POST",
                proxy_evaluation_url,
                {
                    "evaluation_id": evaluation_id,
                    "run_id": proxied_run_id,
                    "task_id": task_id,
                    "evaluator_type": "rule",
                    "score": 1.0,
                    "pass_fail": "pass",
                    "rubric": {"gate": "next_proxy_evidence"},
                    "notes": "Next proxy evaluation evidence proof.",
                },
                token=allowed_token,
            )
            artifact_status, artifact_payload = http_json_status(
                "POST",
                proxy_artifact_url,
                {
                    "artifact_id": artifact_id,
                    "run_id": proxied_run_id,
                    "artifact_type": "delivery_report",
                    "title": "Next proxy evidence artifact",
                    "uri": f"run://{proxied_run_id}",
                    "summary": "Next proxy artifact evidence proof.",
                    "content_hash": "next_proxy_evidence_hash",
                },
                token=allowed_token,
            )
            proxy_manifest_url = f"{next_base}/api/mis/agent-gateway/plan-evidence-manifests"
            manifest_body = {
                "manifest_id": f"pem_{suffix}",
                "plan_id": plan_id,
                "task_id": task_id,
                "run_id": proxied_run_id,
                "mismatch_policy": "block",
                "tool_call_ids": [tool_call_id],
                "evaluation_ids": [evaluation_id],
                "artifact_ids": [artifact_id],
                "verify_now": True,
            }
            manifest_no_token_status, manifest_no_token_payload = http_json_status(
                "POST", proxy_manifest_url, manifest_body
            )
            manifest_missing_scope_status, manifest_missing_scope_payload = http_json_status(
                "POST", proxy_manifest_url, manifest_body, token=observer_token
            )
            manifest_status, manifest_payload = http_json_status(
                "POST", proxy_manifest_url, manifest_body, token=allowed_token
            )

            transcripts.extend([
                no_token_payload,
                missing_scope_payload,
                body_workspace_payload,
                header_workspace_payload,
                other_agent_payload,
                create_payload,
                plan_no_token_payload,
                plan_missing_scope_payload,
                plan_payload,
                run_no_token_payload,
                run_missing_scope_payload,
                run_start_payload,
                heartbeat_no_token_payload,
                heartbeat_missing_scope_payload,
                heartbeat_payload,
                completion_payload,
                revival_payload,
                tool_no_token_payload,
                tool_missing_scope_payload,
                tool_payload,
                evaluation_payload,
                artifact_payload,
                manifest_no_token_payload,
                manifest_missing_scope_payload,
                manifest_payload,
                next_get_payload,
                direct_get_payload,
                next_task_get_payload,
            ])
            created_task = normalize_task(create_payload)
            direct_task = normalize_task(direct_get_payload)
            next_task = normalize_task(next_task_get_payload)

            require(no_token_status == 401, f"missing token should stay unauthorized through Next proxy: {no_token_status} {no_token_payload}")
            require(missing_scope_status == 403 and "tasks:create" in json.dumps(missing_scope_payload, ensure_ascii=False), f"missing scope should be forbidden: {missing_scope_status} {missing_scope_payload}")
            require(body_workspace_status == 403 and "workspace" in json.dumps(body_workspace_payload, ensure_ascii=False).lower(), f"body workspace mismatch should be forbidden: {body_workspace_status} {body_workspace_payload}")
            require(header_workspace_status == 403 and "workspace" in json.dumps(header_workspace_payload, ensure_ascii=False).lower(), f"header workspace mismatch should be forbidden: {header_workspace_status} {header_workspace_payload}")
            require(other_agent_status == 403 and "another agent" in json.dumps(other_agent_payload, ensure_ascii=False).lower(), f"other-agent mismatch should be forbidden: {other_agent_status} {other_agent_payload}")
            require(create_status == 201, f"allowed task create failed through Next proxy: {create_status} {create_payload}")
            require(created_task["task_id"] == task_id, f"created wrong task through Next proxy: {create_payload}")
            require(created_task["workspace_id"] == workspace_id and created_task["owner_agent_id"] == agent_id, f"Next proxy did not preserve Gateway binding: {created_task}")
            require(create_payload.get("token_omitted") is True, f"create payload should omit token: {create_payload}")
            require(plan_no_token_status == 401, f"Agent Plan without token should stay unauthorized: {plan_no_token_status} {plan_no_token_payload}")
            require(
                plan_missing_scope_status == 403
                and "agent_plans:write" in json.dumps(plan_missing_scope_payload, ensure_ascii=False),
                f"Agent Plan missing scope should stay forbidden: {plan_missing_scope_status} {plan_missing_scope_payload}",
            )
            require(
                plan_status == 201
                and (plan_payload.get("agent_plan") or {}).get("plan_id") == plan_id,
                f"Agent Plan failed through Next proxy: {plan_status} {plan_payload}",
            )
            proxied_run = run_start_payload.get("run") or {}
            require(run_no_token_status == 401, f"run start without token should stay unauthorized: {run_no_token_status} {run_no_token_payload}")
            require(run_missing_scope_status == 403 and "runs:write" in json.dumps(run_missing_scope_payload, ensure_ascii=False), f"run start missing scope should stay forbidden: {run_missing_scope_status} {run_missing_scope_payload}")
            require(run_start_status == 201, f"allowed run start failed through Next proxy: {run_start_status} {run_start_payload}")
            require(
                proxied_run.get("task_id") == task_id
                and proxied_run.get("workspace_id") == workspace_id
                and proxied_run.get("agent_id") == agent_id,
                f"Next proxy did not preserve run binding: {run_start_payload}",
            )
            proxied_heartbeat_run = heartbeat_payload.get("run") or {}
            proxied_completion_run = completion_payload.get("run") or {}
            require(heartbeat_no_token_status == 401, f"run heartbeat without token should stay unauthorized: {heartbeat_no_token_status} {heartbeat_no_token_payload}")
            require(heartbeat_missing_scope_status == 403 and "runs:write" in json.dumps(heartbeat_missing_scope_payload, ensure_ascii=False), f"run heartbeat missing scope should stay forbidden: {heartbeat_missing_scope_status} {heartbeat_missing_scope_payload}")
            require(
                heartbeat_status == 200
                and proxied_heartbeat_run.get("run_id") == proxied_run_id
                and proxied_heartbeat_run.get("status") == "running"
                and int(proxied_heartbeat_run.get("duration_ms") or 0) == 1234,
                f"allowed run heartbeat failed through Next proxy: {heartbeat_status} {heartbeat_payload}",
            )
            require(
                completion_status == 200
                and proxied_completion_run.get("run_id") == proxied_run_id
                and proxied_completion_run.get("status") == "completed",
                f"run completion heartbeat failed through Next proxy: {completion_status} {completion_payload}",
            )
            require(revival_status == 409 and "terminal" in json.dumps(revival_payload, ensure_ascii=False).lower(), f"terminal run revival should stay blocked through Next proxy: {revival_status} {revival_payload}")
            require(tool_no_token_status == 401, f"tool evidence without token should stay unauthorized: {tool_no_token_status} {tool_no_token_payload}")
            require(tool_missing_scope_status == 403 and "toolcalls:write" in json.dumps(tool_missing_scope_payload, ensure_ascii=False), f"tool evidence missing scope should stay forbidden: {tool_missing_scope_status} {tool_missing_scope_payload}")
            require(tool_status == 201 and (tool_payload.get("tool_call") or {}).get("run_id") == proxied_run_id, f"tool evidence failed through Next proxy: {tool_status} {tool_payload}")
            require(evaluation_status == 201 and (evaluation_payload.get("evaluation") or {}).get("run_id") == proxied_run_id, f"evaluation evidence failed through Next proxy: {evaluation_status} {evaluation_payload}")
            require(artifact_status == 201 and (artifact_payload.get("artifact") or {}).get("run_id") == proxied_run_id, f"artifact evidence failed through Next proxy: {artifact_status} {artifact_payload}")
            require(manifest_no_token_status == 401, f"manifest without token should stay unauthorized: {manifest_no_token_status} {manifest_no_token_payload}")
            require(
                manifest_missing_scope_status == 403
                and "plan_evidence:write" in json.dumps(manifest_missing_scope_payload, ensure_ascii=False),
                f"manifest missing scope should stay forbidden: {manifest_missing_scope_status} {manifest_missing_scope_payload}",
            )
            require(
                manifest_status == 201
                and (manifest_payload.get("manifest") or {}).get("status") == "verified"
                and (manifest_payload.get("verification") or {}).get("pass") is True,
                f"verified manifest failed through Next proxy: {manifest_status} {manifest_payload}",
            )
            require(next_get_status == 200, f"Next proxy Gateway task readback failed: {next_get_status} {next_get_payload}")
            require(direct_get_status == 200 and next_task_get_status == 200, f"direct/Next task readback failed: direct={direct_get_status} next={next_task_get_status}")
            require(direct_task == next_task == created_task, f"direct API and Next proxy task readback diverged: direct={direct_task} next={next_task} created={created_task}")

            transcript_text = json.dumps(transcripts, ensure_ascii=False, sort_keys=True)
            require(not leaked_secret(transcript_text), "Next proxy response leaked token-like material")
            require(not any(token in transcript_text for token in raw_tokens), "Next proxy response leaked a raw Gateway token")

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "task_id": task_id,
                "workspace_id": workspace_id,
                "agent_id": agent_id,
                "proxy_route": "/api/mis/agent-gateway/tasks",
                "run_start_proxy_route": "/api/mis/agent-gateway/runs/start",
                "run_heartbeat_proxy_route": "/api/mis/agent-gateway/runs/[runId]/heartbeat",
                "tool_call_proxy_route": "/api/mis/agent-gateway/tool-calls",
                "evaluation_proxy_route": "/api/mis/agent-gateway/evaluations/submit",
                "artifact_proxy_route": "/api/mis/agent-gateway/artifacts",
                "agent_plan_proxy_route": "/api/mis/agent-gateway/agent-plans",
                "plan_evidence_proxy_route": "/api/mis/agent-gateway/plan-evidence-manifests",
                "control_plane_mode": "proxy",
                "no_token_status": no_token_status,
                "missing_scope_status": missing_scope_status,
                "body_workspace_status": body_workspace_status,
                "header_workspace_status": header_workspace_status,
                "other_agent_status": other_agent_status,
                "create_status": create_status,
                "agent_plan_status": plan_status,
                "agent_plan_missing_scope_status": plan_missing_scope_status,
                "run_no_token_status": run_no_token_status,
                "run_missing_scope_status": run_missing_scope_status,
                "run_start_status": run_start_status,
                "run_heartbeat_no_token_status": heartbeat_no_token_status,
                "run_heartbeat_missing_scope_status": heartbeat_missing_scope_status,
                "run_heartbeat_status": heartbeat_status,
                "run_completion_status": completion_status,
                "run_terminal_revival_status": revival_status,
                "tool_call_status": tool_status,
                "tool_call_missing_scope_status": tool_missing_scope_status,
                "evaluation_status": evaluation_status,
                "artifact_status": artifact_status,
                "plan_evidence_status": manifest_status,
                "plan_evidence_missing_scope_status": manifest_missing_scope_status,
                "plan_evidence_verified": (manifest_payload.get("verification") or {}).get("pass") is True,
                "gateway_readback_status": next_get_status,
                "direct_task_readback_status": direct_get_status,
                "next_task_readback_status": next_task_get_status,
                "direct_api_matches_next_proxy": True,
                "token_omitted": True,
                "secret_leaked": False,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        for token_id in token_ids:
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
