#!/usr/bin/env python3
"""Verify Next.js customer-worker live controls use prepared-action exact resume."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NEXT_APP = ROOT / "ui" / "next-app"
sys.path.insert(0, str(ROOT))

import server  # noqa: E402

CONTRACT_ID = "nextjs_customer_worker_prepared_action_v1"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)


def start_process(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def wait_http(url: str, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - diagnostic only
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def http_json_status(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw}
        return exc.code, body


def http_text_status(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def post_form_no_redirect(url: str, data: dict[str, str]) -> tuple[int, str]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
            return None

    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, data=encoded, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with opener.open(request, timeout=60) as response:
            return response.status, response.headers.get("Location") or ""
    except urllib.error.HTTPError as exc:
        if exc.code in {301, 302, 303, 307, 308}:
            return exc.code, exc.headers.get("Location") or ""
        raise


def leaked_secret(text: str) -> bool:
    lowered = text.lower()
    markers = ["bearer ", "sk-", "api_key", "access_token", "refresh_token", "password"]
    return any(marker in lowered for marker in markers)


def fake_worker_result(conn, body: dict, calls: list[dict[str, Any]]) -> dict:
    calls.append({"adapter": body.get("adapter"), "async_job": bool(body.get("async_job"))})
    adapter = body.get("adapter") or "openclaw"
    agent_id = body.get("worker_agent_id") or f"agt_next_prepared_{adapter}"
    task_id = body.get("task_id") or server.stable_id("tsk_next_prepared_customer_worker", adapter, str(len(calls)))
    run_id = server.stable_id("run_next_prepared_customer_worker", task_id, str(len(calls)))
    now = server.now_iso()
    server.ensure_gateway_agent(conn, agent_id, name=f"Fake {adapter} Customer Worker", role="Customer Task Worker", runtime_type=adapter)
    server.repo_upsert_task(conn, {
        "task_id": task_id,
        "workspace_id": body.get("workspace_id") or "local-demo",
        "title": f"Fake prepared customer worker {adapter}",
        "description": "Deterministic fake worker result for Next prepared-action smoke.",
        "requester_id": body.get("requester_id") or "usr_customer_demo",
        "owner_agent_id": agent_id,
        "collaborator_agent_ids": json.dumps(body.get("selected_agent_ids") or [], ensure_ascii=False),
        "status": "completed",
        "priority": body.get("priority") or "high",
        "due_date": None,
        "acceptance_criteria": "Fake worker must produce ledger evidence.",
        "risk_level": body.get("risk_level") or "medium",
        "budget_limit_usd": 1.0,
        "created_at": now,
        "updated_at": now,
    })
    server.repo_upsert_run(conn, {
        "run_id": run_id,
        "workspace_id": body.get("workspace_id") or "local-demo",
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": adapter,
        "status": "completed",
        "started_at": now,
        "ended_at": now,
        "duration_ms": 123,
        "input_summary": "Fake prepared customer worker input hash only.",
        "output_summary": "Fake prepared customer worker completed.",
        "model_provider": adapter,
        "model_name": f"{adapter}-fake",
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cost_usd": 0.0,
        "error_type": None,
        "error_message": None,
        "trace_id": None,
        "parent_run_id": None,
        "delegation_id": f"customer-worker:{adapter}",
        "approval_required": 0,
        "created_at": now,
    })
    tool_call_id = server.stable_id("tc_next_prepared_customer_worker", run_id)
    server.repo_upsert_tool_call(conn, {
        "tool_call_id": tool_call_id,
        "run_id": run_id,
        "agent_id": agent_id,
        "tool_name": "fake.customer_worker",
        "tool_version": "v1",
        "tool_category": "custom",
        "normalized_args_json": json.dumps({"adapter": adapter, "raw_request_omitted": True}, sort_keys=True),
        "target_resource": "fake://customer-worker",
        "risk_level": "medium",
        "status": "completed",
        "result_summary": "Fake worker completed.",
        "side_effect_id": None,
        "started_at": now,
        "ended_at": now,
        "created_at": now,
    })
    server.repo_upsert_evaluation(conn, server.quality_gate_for_run({"run_id": run_id, "task_id": task_id, "agent_id": agent_id, "status": "completed"}))
    artifact_id = server.stable_id("art_next_prepared_customer_worker", run_id)
    server.repo_upsert_artifact(conn, {
        "artifact_id": artifact_id,
        "workspace_id": body.get("workspace_id") or "local-demo",
        "task_id": task_id,
        "run_id": run_id,
        "artifact_type": "customer_delivery",
        "title": "Fake prepared customer worker delivery",
        "uri": f"ledger://artifacts/{artifact_id}",
        "content_hash": server.stable_hash({"run_id": run_id, "raw_output_omitted": True}),
        "summary": "Fake delivery summary with raw output omitted.",
        "created_at": now,
    })
    server.runtime_event(conn, server.runtime_connector_for_adapter(adapter), "fake_customer_worker.completed", "completed", run_id=run_id, task_id=task_id, agent_id=agent_id, output_summary="Fake worker completed.")
    server.audit(conn, "system", "fake-worker", "fake.customer_worker.completed", "runs", run_id, None, {"status": "completed"}, {"raw_output_omitted": True})
    conn.commit()
    return {
        "ok": True,
        "adapter": adapter,
        "agent_id": agent_id,
        "task_id": task_id,
        "run_id": run_id,
        "artifact_id": artifact_id,
        "duration_ms": 123,
        "output_summary": "Fake prepared customer worker completed.",
        "worker_result": {
            "ok": True,
            "raw_output_omitted": True,
            "results": [{
                "processed": True,
                "task_id": task_id,
                "run_id": run_id,
                "output_summary": "Fake prepared customer worker completed.",
            }],
        },
        "error": None,
        "token_omitted": True,
    }


def approve(next_base: str, approval_id: str) -> dict[str, Any]:
    status, payload = http_json_status("POST", f"{next_base}/api/mis/approvals/{urllib.parse.quote(approval_id)}/approve", {})
    require(status == 200 and payload.get("decision") == "approved", f"approval failed: {status} {payload}")
    return payload


def prepared_action_readback(next_base: str, action_id: str, *, include_consumed: bool = False) -> dict[str, Any]:
    suffix = "?limit=20"
    if include_consumed:
        suffix += "&include_consumed=true"
    status, payload = http_json_status("GET", f"{next_base}/api/mis/workflows/customer-worker-prepared-actions{suffix}")
    require(status == 200, f"prepared-action readback failed: {status} {payload}")
    require(payload.get("raw_request_omitted") is True and payload.get("raw_result_omitted") is True, f"prepared-action payload omission flags missing: {payload}")
    actions = payload.get("prepared_actions") or []
    match = next((item for item in actions if item.get("prepared_action_id") == action_id), None)
    require(match, f"prepared action {action_id} missing from readback: {payload}")
    forbidden = {"normalized_args_json", "result_json", "snapshot_ref"}
    leaked_fields = sorted(forbidden.intersection(match))
    require(not leaked_fields, f"prepared-action readback leaked raw fields: {leaked_fields} in {match}")
    require(match.get("raw_request_omitted") is True and match.get("raw_result_omitted") is True, f"prepared-action row omission flags missing: {match}")
    return match


def prepared_body(adapter: str, *, async_job: bool = False) -> dict[str, Any]:
    return {
        "adapter": adapter,
        "confirm_run": True,
        "title": "Next async customer worker job" if async_job else "Next customer worker dispatch",
        "description": "Next.js submits one safe async customer-worker job and reads job status back through the MIS proxy." if async_job else "Next.js dispatches one safe mock customer-worker task and reads back ledger evidence.",
        "acceptance_criteria": "Workflow job must complete with run, artifact, delivery approval, and verified plan evidence without token leakage." if async_job else "Worker must write run, tool, evaluation, audit, artifact, memory, approval, and verified plan evidence.",
        "priority": "high",
        "risk_level": "medium",
        "worker_agent_id": "agt_next_customer_worker_async" if async_job else "agt_next_customer_worker",
        "selected_agent_ids": ["agt_next_customer_worker_async" if async_job else "agt_next_customer_worker"],
    }


def exercise_sync_proxy(next_base: str, calls: list[dict[str, Any]], transcripts: list[Any]) -> dict[str, Any]:
    body = prepared_body("openclaw")
    status, prepare = http_json_status("POST", f"{next_base}/api/mis/workflows/customer-worker-task", body)
    transcripts.append(prepare)
    require(status == 202, f"sync prepare failed: {status} {prepare}")
    require(prepare.get("requires_approval") is True and prepare.get("provider_call_performed") is False, f"sync prepare contract wrong: {prepare}")
    require(len(calls) == 0, f"sync provider called before approval: {calls}")
    action_id = str(prepare.get("prepared_action_id") or "")
    request_hash = str(prepare.get("request_hash") or "")
    require(action_id and request_hash and prepare.get("approval_id"), f"sync prepare missing ids: {prepare}")
    waiting = prepared_action_readback(next_base, action_id)
    require(waiting.get("status") == "waiting_approval" and waiting.get("approval_decision") == "pending", f"sync waiting readback wrong: {waiting}")
    require(waiting.get("request_hash") == request_hash and waiting.get("can_resume") is False, f"sync waiting resume guard wrong: {waiting}")

    premature_status, premature = http_json_status("POST", f"{next_base}/api/mis/workflows/customer-worker-task", {**body, "prepared_action_id": action_id, "request_hash": request_hash})
    transcripts.append(premature)
    require(premature_status == 428 and premature.get("error") == "approval_required", f"sync premature wrong: {premature_status} {premature}")

    approve(next_base, str(prepare["approval_id"]))
    approved = prepared_action_readback(next_base, action_id)
    require(approved.get("status") == "approved" and approved.get("can_resume") is True, f"sync approved readback wrong: {approved}")
    mismatch_status, mismatch = http_json_status("POST", f"{next_base}/api/mis/workflows/customer-worker-task", {**body, "title": "Changed title", "prepared_action_id": action_id, "request_hash": request_hash})
    transcripts.append(mismatch)
    require(mismatch_status == 409 and mismatch.get("error") == "prepared_action_request_hash_mismatch", f"sync mismatch wrong: {mismatch_status} {mismatch}")
    require(len(calls) == 0, f"sync mismatch called provider: {calls}")

    resume_status, resume = http_json_status("POST", f"{next_base}/api/mis/workflows/customer-worker-task", {**body, "prepared_action_id": action_id, "request_hash": request_hash})
    transcripts.append(resume)
    require(resume_status == 201 and resume.get("ok") is True, f"sync resume failed: {resume_status} {resume}")
    require(resume.get("prepared_action_status") == "consumed", f"sync action not consumed: {resume}")
    require(len(calls) == 1, f"sync provider not called exactly once: {calls}")
    consumed = prepared_action_readback(next_base, action_id, include_consumed=True)
    require(consumed.get("status") == "consumed" and consumed.get("can_resume") is False, f"sync consumed readback wrong: {consumed}")

    replay_status, replay = http_json_status("POST", f"{next_base}/api/mis/workflows/customer-worker-task", {**body, "prepared_action_id": action_id, "request_hash": request_hash})
    transcripts.append(replay)
    require(replay_status == 409 and replay.get("error") == "prepared_action_already_consumed", f"sync replay wrong: {replay_status} {replay}")
    require(len(calls) == 1, f"sync replay called provider: {calls}")
    return resume


def exercise_sync_form(next_base: str, calls: list[dict[str, Any]], transcripts: list[Any]) -> dict[str, str]:
    form_body = {key: str(value) for key, value in prepared_body("openclaw").items() if key not in {"confirm_run", "selected_agent_ids"}}
    form_body.update({
        "title": "Next prepared queue custom resume",
        "description": "Custom dispatch text proves the ledger-derived resume form survives page refresh without raw JSON exposure.",
        "acceptance_criteria": "The prepared action queue must resume this exact custom request by safe projected fields.",
        "priority": "medium",
        "risk_level": "high",
    })
    status, location = post_form_no_redirect(f"{next_base}/workspace/dispatch/customer-worker", form_body)
    transcripts.append(location)
    require(status == 303, f"sync form prepare did not redirect: {status} {location}")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
    require(query.get("customer_worker_status") == ["waiting_approval"], f"sync form did not wait for approval: {location}")
    action_id = (query.get("customer_worker_prepared_action_id") or [""])[0]
    request_hash = (query.get("customer_worker_request_hash") or [""])[0]
    approval_id = (query.get("customer_worker_approval_id") or [""])[0]
    require(action_id and request_hash and approval_id, f"sync form missing prepared ids: {location}")
    approve(next_base, approval_id)
    approved = prepared_action_readback(next_base, action_id)
    require(approved.get("can_resume") is True and approved.get("request_hash") == request_hash, f"sync form approved queue wrong: {approved}")
    resume_form = approved.get("resume_form") or {}
    require(resume_form.get("title") == form_body["title"], f"sync form safe resume title missing: {approved}")
    require(resume_form.get("description") == form_body["description"], f"sync form safe resume description missing: {approved}")
    require(resume_form.get("acceptance_criteria") == form_body["acceptance_criteria"], f"sync form safe resume acceptance missing: {approved}")
    page_status, page_html = http_text_status(f"{next_base}/workspace/dispatch")
    require(page_status == 200, f"dispatch page failed while rendering prepared queue: {page_status}")
    require("customer-worker-prepared-actions" in page_html and "Prepared worker actions" in page_html and "Resume worker" in page_html, "dispatch page did not render ledger-derived prepared action resume controls")

    resume_body = {
        "adapter": str(approved.get("adapter") or "openclaw"),
        "prepared_action_id": action_id,
        "request_hash": request_hash,
        "title": str(resume_form.get("title") or ""),
        "worker_agent_id": str(resume_form.get("worker_agent_id") or "agt_next_customer_worker"),
        "description": str(resume_form.get("description") or ""),
        "acceptance_criteria": str(resume_form.get("acceptance_criteria") or ""),
        "priority": str(resume_form.get("priority") or "high"),
        "risk_level": str(resume_form.get("risk_level") or "medium"),
    }
    resume_status, resume_location = post_form_no_redirect(f"{next_base}/workspace/dispatch/customer-worker", resume_body)
    transcripts.append(resume_location)
    require(resume_status == 303, f"sync form resume did not redirect: {resume_status} {resume_location}")
    resume_query = urllib.parse.parse_qs(urllib.parse.urlparse(resume_location).query)
    require(resume_query.get("customer_worker_status") == ["started"], f"sync form did not report started: {resume_location}")
    require(resume_query.get("customer_worker_prepared_status") == ["consumed"], f"sync form did not report consumed: {resume_location}")
    require(len(calls) == 2, f"sync form did not call provider once: {calls}")
    return {key: (values or [""])[0] for key, values in resume_query.items()}


def exercise_async_proxy(next_base: str, transcripts: list[Any]) -> dict[str, Any]:
    body = prepared_body("hermes", async_job=True)
    status, prepare = http_json_status("POST", f"{next_base}/api/mis/workflows/customer-worker-task/submit", body)
    transcripts.append(prepare)
    require(status == 202 and prepare.get("requires_approval") is True and not prepare.get("job_id"), f"async prepare failed: {status} {prepare}")
    action_id = str(prepare.get("prepared_action_id") or "")
    request_hash = str(prepare.get("request_hash") or "")
    require(action_id and request_hash and prepare.get("approval_id"), f"async prepare missing ids: {prepare}")
    waiting = prepared_action_readback(next_base, action_id)
    require(waiting.get("status") == "waiting_approval" and waiting.get("async_job") is True, f"async waiting readback wrong: {waiting}")
    premature_status, premature = http_json_status("POST", f"{next_base}/api/mis/workflows/customer-worker-task/submit", {**body, "prepared_action_id": action_id, "request_hash": request_hash})
    transcripts.append(premature)
    require(premature_status == 428 and premature.get("error") == "approval_required", f"async premature wrong: {premature_status} {premature}")
    approve(next_base, str(prepare["approval_id"]))
    approved = prepared_action_readback(next_base, action_id)
    require(approved.get("can_resume") is True and approved.get("adapter") == "hermes", f"async approved readback wrong: {approved}")
    resume_status, resume = http_json_status("POST", f"{next_base}/api/mis/workflows/customer-worker-task/submit", {**body, "prepared_action_id": action_id, "request_hash": request_hash})
    transcripts.append(resume)
    require(resume_status == 202 and resume.get("ok") is True and resume.get("job_id"), f"async resume failed: {resume_status} {resume}")
    require(resume.get("prepared_action_status") == "consumed", f"async action not consumed: {resume}")
    consumed = prepared_action_readback(next_base, action_id, include_consumed=True)
    require(consumed.get("status") == "consumed" and consumed.get("async_job") is True, f"async consumed readback wrong: {consumed}")
    replay_status, replay = http_json_status("POST", f"{next_base}/api/mis/workflows/customer-worker-task/submit", {**body, "prepared_action_id": action_id, "request_hash": request_hash})
    transcripts.append(replay)
    require(replay_status == 409 and replay.get("error") == "prepared_action_already_consumed", f"async replay wrong: {replay_status} {replay}")
    return resume


def main() -> int:
    if not shutil_which("npx"):
        print(json.dumps({"ok": False, "error": "npx is required for Next.js prepared-action smoke"}, indent=2), file=sys.stderr)
        return 2

    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"
    calls: list[dict[str, Any]] = []
    transcripts: list[Any] = []
    processes: list[subprocess.Popen] = []
    httpd = None
    original_db_path = server.DB_PATH
    original_dispatch = server.dispatch_local_worker_once
    original_readiness = server.worker_adapter_readiness

    with tempfile.TemporaryDirectory(prefix="agentops-next-customer-worker-prepared-") as tmp:
        try:
            server.DB_PATH = Path(tmp) / "agentops.sqlite"
            server.seed(reset=True)
            server.worker_adapter_readiness = lambda conn, refresh=True: {
                "provider": "agentops-worker",
                "status": "ready",
                "summary": {
                    "ready_adapters": ["mock", "hermes", "openclaw"],
                    "live_ready_adapters": ["hermes", "openclaw"],
                    "recommended_adapter": "openclaw",
                },
                "adapters": {
                    "mock": {"adapter": "mock", "readiness": "ready", "ok": True},
                    "hermes": {"adapter": "hermes", "readiness": "ready", "ok": True},
                    "openclaw": {"adapter": "openclaw", "readiness": "ready", "ok": True},
                },
                "live_execution_performed": False,
                "token_omitted": True,
            }
            server.dispatch_local_worker_once = lambda conn, body: fake_worker_result(conn, body, calls)
            with server.db() as conn:
                server.refresh_runtime_connectors(conn)
                conn.execute("UPDATE runtime_connectors SET trust_status='trusted', trust_note=NULL WHERE provider IN ('openclaw','hermes')")
                conn.commit()

            httpd = server.ThreadingHTTPServer(("127.0.0.1", api_port), server.Handler)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env.pop("AGENTOPS_API_KEY", None)
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/api/mis/dashboard/metrics")

            sync_resume = exercise_sync_proxy(next_base, calls, transcripts)
            sync_form = exercise_sync_form(next_base, calls, transcripts)
            async_resume = exercise_async_proxy(next_base, transcripts)

            page_status, page_payload = http_json_status("GET", f"{next_base}/api/mis/workflows/jobs")
            transcripts.append(page_payload)
            require(page_status == 200, f"job list failed after async resume: {page_status} {page_payload}")

            serialized = json.dumps(transcripts, ensure_ascii=False)
            require(not leaked_secret(serialized), "Next customer-worker prepared-action smoke leaked token-like material")
            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "proxy_route": "/api/mis/workflows/customer-worker-task",
                "async_proxy_route": "/api/mis/workflows/customer-worker-task/submit",
                "form_route": "/workspace/dispatch/customer-worker",
                "provider_call_count": len(calls),
                "sync_prepared_action": sync_resume.get("prepared_action_id"),
                "sync_form_task": sync_form.get("customer_worker_task_id"),
                "async_prepared_action": async_resume.get("prepared_action_id"),
                "async_job_id": async_resume.get("job_id"),
                "raw_request_omitted": True,
                "raw_result_omitted": True,
                "token_omitted": True,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        finally:
            if httpd:
                httpd.shutdown()
            for proc in processes:
                proc.terminate()
            for proc in processes:
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
            server.DB_PATH = original_db_path
            server.dispatch_local_worker_once = original_dispatch
            server.worker_adapter_readiness = original_readiness


def shutil_which(name: str) -> str | None:
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(folder) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


if __name__ == "__main__":
    raise SystemExit(main())
