#!/usr/bin/env python3
"""Verify Next.js can submit and read a safe async customer-worker job."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "nextjs_customer_worker_async_job_v1"

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


def http_json_status(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}


def http_text_status(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=90) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def post_form_no_redirect(url: str, payload: dict[str, str]) -> tuple[int, str]:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=120) as response:
            return int(response.status), response.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        if exc.code in {302, 303, 307, 308}:
            return int(exc.code), exc.headers.get("Location", "")
        raise


def workflow_job_ids(payload: Any) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    return {str(item.get("job_id") or "") for item in payload.get("jobs") or [] if isinstance(item, dict) and item.get("job_id")}


def worker_payload(title: str, *, adapter: str = "mock") -> dict[str, Any]:
    return {
        "adapter": adapter,
        "confirm_run": adapter == "mock",
        "title": title,
        "description": "Next.js customer-worker async job parity smoke writes ledger evidence through the MIS API.",
        "acceptance_criteria": "Workflow job must complete with run, artifact, approval, and verified plan evidence.",
        "priority": "high",
        "risk_level": "medium",
        "worker_agent_id": f"agt_next_customer_worker_async_{adapter}",
        "selected_agent_ids": [f"agt_next_customer_worker_async_{adapter}"],
    }


def wait_for_job(next_base: str, job_id: str, *, timeout_sec: float = 70.0) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last_payload: dict[str, Any] = {}
    while time.time() < deadline:
        status, payload = http_json_status("GET", f"{next_base}/api/mis/workflows/jobs/{job_id}")
        require(status == 200, f"job readback failed: {status} {payload}")
        last_payload = payload
        job = payload.get("job") or {}
        if job.get("status") in {"completed", "failed"}:
            return payload
        time.sleep(0.5)
    raise AssertionError(f"job did not reach terminal state: {last_payload}")


def assert_completed_job(label: str, payload: dict[str, Any]) -> tuple[str, str, str, str]:
    job = payload.get("job") or {}
    result = job.get("result") or {}
    evidence = result.get("evidence") or {}
    require(job.get("workflow_type") == "customer_worker_task", f"{label} wrong workflow type: {job}")
    require(job.get("status") == "completed", f"{label} job did not complete: {job}")
    require(job.get("raw_request_omitted") is True and job.get("token_omitted") is True, f"{label} job omission flags missing: {job}")
    require(result.get("workflow") == "customer_worker_task", f"{label} wrong result workflow: {result}")
    require(result.get("ok") is True, f"{label} result failed: {result}")
    require(result.get("plan_evidence_pass") is True, f"{label} plan evidence did not pass: {result}")
    task_id = str(job.get("result_task_id") or result.get("task_id") or "")
    run_id = str(job.get("result_run_id") or result.get("run_id") or "")
    artifact_id = str(job.get("result_artifact_id") or result.get("artifact_id") or "")
    manifest_id = str(result.get("plan_evidence_manifest_id") or "")
    require(task_id and run_id and artifact_id and manifest_id, f"{label} missing result ids: {payload}")
    for key in ("tool_calls", "evaluations", "audit_logs", "artifacts", "approvals", "plan_evidence_manifests"):
        require(int(evidence.get(key) or 0) >= 1, f"{label} missing {key} evidence: {evidence}")
    return task_id, run_id, artifact_id, manifest_id


def assert_next_evidence_readback(next_base: str, task_id: str, run_id: str, artifact_id: str, manifest_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    task_status, task_payload = http_json_status("GET", f"{next_base}/api/mis/tasks/{task_id}")
    require(task_status == 200, f"task readback failed: {task_status} {task_payload}")
    require(any(row.get("artifact_id") == artifact_id for row in task_payload.get("artifacts") or []), f"task missing async artifact: {task_payload}")

    run_status, run_payload = http_json_status("GET", f"{next_base}/api/mis/runs/{run_id}")
    require(run_status == 200, f"run readback failed: {run_status} {run_payload}")
    require((run_payload.get("run") or {}).get("status") == "completed", f"run did not complete: {run_payload}")
    require(len(run_payload.get("tool_calls") or []) >= 1, f"run missing tool calls: {run_payload}")
    require(len(run_payload.get("evaluations") or []) >= 1, f"run missing evaluations: {run_payload}")

    manifest_status, manifest_payload = http_json_status(
        "GET",
        f"{next_base}/api/mis/agent-gateway/plan-evidence-manifests/{manifest_id}/verify",
    )
    require(manifest_status == 200, f"manifest readback failed: {manifest_status} {manifest_payload}")
    require((manifest_payload.get("verification") or {}).get("pass") is True, f"manifest did not verify: {manifest_payload}")
    return task_payload, run_payload, manifest_payload


def main() -> int:
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": "npx is required"}, indent=2), file=sys.stderr)
        return 1

    processes: list[subprocess.Popen[str]] = []
    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"
    transcripts: list[Any] = []

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-customer-worker-job-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            reset_env = os.environ.copy()
            reset_env.pop("AGENTOPS_API_KEY", None)
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset_env["AGENTOPS_BASE_URL"] = api_base
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = os.environ.copy()
            api_env.pop("AGENTOPS_API_KEY", None)
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_env["AGENTOPS_BASE_URL"] = api_base
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env.pop("AGENTOPS_API_KEY", None)
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/api/mis/dashboard/metrics")

            before_status, before_payload = http_json_status("GET", f"{api_base}/api/workflows/jobs")
            require(before_status == 200, f"pre-block job list failed: {before_status} {before_payload}")
            before_ids = workflow_job_ids(before_payload)
            block_status, block_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/workflows/customer-worker-task/submit",
                worker_payload("Blocked Next async customer-worker proxy smoke", adapter="hermes"),
            )
            transcripts.append(block_payload)
            require(block_status == 403, f"non-mock async proxy did not fail closed: {block_status} {block_payload}")
            require(block_payload.get("error") == "customer_worker_mock_only_next_parity", f"wrong non-mock async proxy error: {block_payload}")
            after_status, after_payload = http_json_status("GET", f"{api_base}/api/workflows/jobs")
            require(after_status == 200, f"post-block job list failed: {after_status} {after_payload}")
            require(workflow_job_ids(after_payload) == before_ids, "non-mock async proxy created or removed workflow jobs")

            proxy_status, proxy_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/workflows/customer-worker-task/submit",
                worker_payload("Next async customer-worker proxy smoke"),
            )
            transcripts.append(proxy_payload)
            require(proxy_status == 202, f"async proxy submit returned {proxy_status}: {proxy_payload}")
            proxy_job_id = str(proxy_payload.get("job_id") or "")
            require(proxy_job_id and proxy_payload.get("provider") == "agentops-workflow-job", f"async proxy missing job id: {proxy_payload}")
            proxy_job_payload = wait_for_job(next_base, proxy_job_id)
            transcripts.append(proxy_job_payload)
            proxy_task_id, proxy_run_id, proxy_artifact_id, proxy_manifest_id = assert_completed_job("proxy async job", proxy_job_payload)
            transcripts.extend(assert_next_evidence_readback(next_base, proxy_task_id, proxy_run_id, proxy_artifact_id, proxy_manifest_id))

            form_block_before_status, form_block_before_payload = http_json_status("GET", f"{api_base}/api/workflows/jobs")
            require(form_block_before_status == 200, f"pre-form-block job list failed: {form_block_before_status} {form_block_before_payload}")
            form_block_before_ids = workflow_job_ids(form_block_before_payload)
            form_block_status, form_block_location = post_form_no_redirect(
                f"{next_base}/workspace/dispatch/customer-worker-job",
                {"adapter": "openclaw", "title": "Blocked async customer-worker form smoke"},
            )
            transcripts.append(form_block_location)
            require(form_block_status == 303, f"non-mock async form did not redirect: {form_block_status} {form_block_location}")
            form_block_query = urllib.parse.parse_qs(urllib.parse.urlparse(form_block_location).query)
            require(form_block_query.get("customer_worker_job_status") == ["blocked"], f"non-mock async form did not report blocked: {form_block_location}")
            require(form_block_query.get("customer_worker_error") == ["customer_worker_mock_only_next_parity"], f"non-mock async form wrong error: {form_block_location}")
            form_block_after_status, form_block_after_payload = http_json_status("GET", f"{api_base}/api/workflows/jobs")
            require(form_block_after_status == 200, f"post-form-block job list failed: {form_block_after_status} {form_block_after_payload}")
            require(workflow_job_ids(form_block_after_payload) == form_block_before_ids, "non-mock async form created or removed workflow jobs")

            form_status, form_location = post_form_no_redirect(
                f"{next_base}/workspace/dispatch/customer-worker-job",
                {
                    "adapter": "mock",
                    "title": "Next async customer-worker form smoke",
                    "worker_agent_id": "agt_next_customer_worker_async_form",
                    "description": "Next form fallback submits the safe async customer worker job.",
                    "acceptance_criteria": "Job proof must be readable through the Next proxy.",
                },
            )
            transcripts.append(form_location)
            require(form_status == 303, f"mock async form did not redirect: {form_status} {form_location}")
            form_query = urllib.parse.parse_qs(urllib.parse.urlparse(form_location).query)
            require(form_query.get("customer_worker_job_status") == ["submitted"], f"mock async form did not report submitted: {form_location}")
            form_job_id = (form_query.get("customer_worker_job_id") or [""])[0]
            require(form_job_id, f"mock async form missing job id: {form_location}")
            form_job_payload = wait_for_job(next_base, form_job_id)
            transcripts.append(form_job_payload)
            form_task_id, form_run_id, form_artifact_id, form_manifest_id = assert_completed_job("form async job", form_job_payload)
            transcripts.extend(assert_next_evidence_readback(next_base, form_task_id, form_run_id, form_artifact_id, form_manifest_id))

            page_status, page_html = http_text_status(
                f"{next_base}/workspace/dispatch?customer_worker_job_status=submitted&customer_worker_job_id={urllib.parse.quote(form_job_id)}"
            )
            require(page_status == 200, f"dispatch page render failed: {page_status}")
            require("Async worker jobs" in page_html and form_job_id in page_html, "dispatch page did not render async job evidence")
            transcripts.append({"page_status": page_status, "page_contains_job": form_job_id in page_html})

            transcript_text = json.dumps(transcripts, ensure_ascii=False, sort_keys=True)
            require(not leaked_secret(transcript_text), "Next async customer-worker job leaked token-like material")

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "proxy_route": "/api/mis/workflows/customer-worker-task/submit",
                "form_route": "/workspace/dispatch/customer-worker-job",
                "job_readback": "/api/mis/workflows/jobs/:job_id",
                "evidence_readback": "/api/mis/runs/:run_id and /api/mis/agent-gateway/plan-evidence-manifests/:id/verify",
                "non_mock_proxy_status": block_status,
                "non_mock_form_status": form_block_status,
                "non_mock_error": "customer_worker_mock_only_next_parity",
                "proxy_job_id": proxy_job_id,
                "proxy_task_id": proxy_task_id,
                "proxy_run_id": proxy_run_id,
                "proxy_artifact_id": proxy_artifact_id,
                "proxy_manifest_id": proxy_manifest_id,
                "form_job_id": form_job_id,
                "form_task_id": form_task_id,
                "form_run_id": form_run_id,
                "form_artifact_id": form_artifact_id,
                "form_manifest_id": form_manifest_id,
                "dispatch_page_status": page_status,
                "adapter": "mock",
                "secret_leaked": False,
                "token_omitted": True,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
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
