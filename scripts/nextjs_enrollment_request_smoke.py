#!/usr/bin/env python3
"""Verify Next.js can request Agent Gateway enrollment without issuing tokens."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "nextjs_enrollment_request_v1"
WORKER_SCOPES = [
    "agents:heartbeat",
    "tasks:read",
    "tasks:claim",
    "runs:write",
    "toolcalls:write",
    "evaluations:submit",
    "audit:write",
]

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
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}


def post_form_no_redirect(url: str, payload: dict[str, str]) -> tuple[int, str]:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=90) as response:
            return int(response.status), response.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        if exc.code in {302, 303, 307, 308}:
            return int(exc.code), exc.headers.get("Location", "")
        raise


def enrollment_token_ids(payload: Any) -> set[str]:
    enrollments = payload.get("enrollments") if isinstance(payload, dict) else []
    if not isinstance(enrollments, list):
        return set()
    return {str(item.get("token_id") or item.get("token_ref") or "") for item in enrollments if isinstance(item, dict)}


def assert_no_token(label: str, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    require("agtok_" not in text, f"{label} leaked a raw Agent Gateway token: {payload}")
    require(not leaked_secret(text), f"{label} leaked token-like material")


def request_payload(agent_id: str, name: str) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "name": name,
        "role": "Remote AI Digital Employee",
        "runtime_type": "mock",
        "workspace_id": "local-demo",
        "scopes": WORKER_SCOPES,
        "ttl_days": 30,
        "heartbeat_timeout_sec": 300,
        "reason": "Next enrollment request smoke proves approval-gated remote worker enrollment.",
    }


def main() -> int:
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "error": "npx is required for Next.js enrollment smoke"}, indent=2), file=sys.stderr)
        return 1

    processes: list[subprocess.Popen[str]] = []
    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-enrollment-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            reset_env = os.environ.copy()
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset_env["AGENTOPS_BASE_URL"] = api_base
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = os.environ.copy()
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_env["AGENTOPS_BASE_URL"] = api_base
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace/agents")

            list_before_status, list_before = http_json_status("GET", f"{api_base}/api/agent-gateway/enrollments")
            require(list_before_status == 200, f"pre-enrollment list failed: {list_before_status} {list_before}")
            before_token_ids = enrollment_token_ids(list_before)

            preview_status, preview = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/enrollment/policy-preview", {
                "runtime_type": "mock",
                "workspace_id": "local-demo",
                "scopes": WORKER_SCOPES,
            })
            require(preview_status == 200, f"Next policy preview failed: {preview_status} {preview}")
            require(preview.get("operation") == "enrollment_policy_preview", f"wrong preview operation: {preview}")
            require(preview.get("safety", {}).get("read_only") is True, f"preview was not read-only: {preview}")
            require(preview.get("safety", {}).get("ledger_mutated") is False, f"preview mutated ledger: {preview}")
            require(preview.get("token_omitted") is True, f"preview token omission missing: {preview}")
            assert_no_token("policy preview", preview)

            invalid_preview_status, invalid_preview = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/enrollment/policy-preview", {
                "runtime_type": "mock",
                "workspace_id": "local-demo",
                "scopes": ["agents:heartbeat", "root:all"],
            })
            require(invalid_preview_status == 400, f"invalid scope preview was not rejected by Next guard: {invalid_preview_status} {invalid_preview}")
            require(invalid_preview.get("error") == "invalid_scopes", f"invalid preview error mismatch: {invalid_preview}")

            blocked_status, blocked = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/enrollment/create", request_payload(f"agt_next_blocked_{stamp}", "Blocked Next Direct Token"))
            require(blocked_status == 403, f"Next direct enrollment create did not fail closed: {blocked_status} {blocked}")
            require(blocked.get("error") == "enrollment_token_issue_not_allowed_next_parity", f"wrong blocked create error: {blocked}")
            assert_no_token("blocked direct token issue", blocked)

            list_after_block_status, list_after_block = http_json_status("GET", f"{api_base}/api/agent-gateway/enrollments")
            require(list_after_block_status == 200, f"post-block list failed: {list_after_block_status} {list_after_block}")
            require(enrollment_token_ids(list_after_block) == before_token_ids, "blocked Next token issue changed enrollment tokens")

            req_agent_id = f"agt_next_enroll_req_{stamp}"
            request_status, requested = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/enrollment/request", request_payload(req_agent_id, "Next Approval Remote Worker"))
            require(request_status == 201, f"Next enrollment request failed: {request_status} {requested}")
            require(requested.get("token_issued") is False and requested.get("token_omitted") is True, f"request token flags wrong: {requested}")
            request_info = requested.get("request") or {}
            approval_info = requested.get("approval") or {}
            request_id = str(request_info.get("request_id") or "")
            approval_id = str(approval_info.get("approval_id") or request_info.get("approval_id") or "")
            task_id = str(request_info.get("task_id") or "")
            run_id = str(request_info.get("run_id") or "")
            require(request_id and approval_id and task_id and run_id, f"request missing ids: {requested}")
            require(request_info.get("agent_id") == req_agent_id, f"request agent mismatch: {requested}")
            assert_no_token("approval-gated request", requested)

            blocked_issue_status, blocked_issue = http_json_status("POST", f"{next_base}/api/mis/agent-gateway/enrollment/issue-approved", {"approval_id": approval_id})
            require(blocked_issue_status == 403, f"Next approved-token issue was not blocked in this slice: {blocked_issue_status} {blocked_issue}")
            require(blocked_issue.get("error") == "enrollment_token_issue_not_allowed_next_parity", f"wrong issue-approved block error: {blocked_issue}")
            assert_no_token("blocked issue-approved", blocked_issue)

            approvals_status, approvals = http_json_status("GET", f"{next_base}/api/mis/approvals")
            require(approvals_status == 200 and isinstance(approvals, list), f"approval readback failed: {approvals_status} {approvals}")
            approval_row = next((item for item in approvals if isinstance(item, dict) and item.get("approval_id") == approval_id), None)
            require(approval_row and approval_row.get("decision") == "pending", f"pending approval not found through Next proxy: {approvals}")

            form_agent_id = f"agt_next_enroll_form_{stamp}"
            form_status, form_location = post_form_no_redirect(f"{next_base}/workspace/agents/enrollment-request", {
                "agent_id": form_agent_id,
                "name": "Next Form Remote Worker",
                "role": "Remote AI Digital Employee",
                "runtime_type": "mock",
                "workspace_id": "local-demo",
                "scopes": ",".join(WORKER_SCOPES),
                "ttl_days": "30",
                "heartbeat_timeout_sec": "300",
                "reason": "Next form fallback requested approval-gated enrollment.",
            })
            require(form_status == 303, f"form fallback did not redirect with 303: {form_status} {form_location}")
            form_query = urllib.parse.parse_qs(urllib.parse.urlparse(form_location).query)
            require(form_query.get("enrollment_status") == ["requested"], f"form fallback did not report requested: {form_location}")
            form_request_id = (form_query.get("request_id") or [""])[0]
            form_approval_id = (form_query.get("approval_id") or [""])[0]
            require(form_request_id and form_approval_id, f"form fallback missing request/approval ids: {form_location}")
            require("token" not in urllib.parse.urlparse(form_location).query.lower(), f"form redirect leaked token field: {form_location}")

            invalid_form_status, invalid_form_location = post_form_no_redirect(f"{next_base}/workspace/agents/enrollment-request", {
                "agent_id": f"agt_next_enroll_invalid_{stamp}",
                "name": "Invalid Scope Worker",
                "runtime_type": "mock",
                "workspace_id": "local-demo",
                "scopes": "agents:heartbeat,root:all",
            })
            require(invalid_form_status == 303, f"invalid form did not redirect: {invalid_form_status} {invalid_form_location}")
            invalid_form_query = urllib.parse.parse_qs(urllib.parse.urlparse(invalid_form_location).query)
            require(invalid_form_query.get("enrollment_status") == ["failed"], f"invalid form did not fail closed: {invalid_form_location}")
            require(invalid_form_query.get("error") == ["invalid_scopes"], f"invalid form wrong error: {invalid_form_location}")

            list_after_request_status, list_after_request = http_json_status("GET", f"{api_base}/api/agent-gateway/enrollments")
            require(list_after_request_status == 200, f"post-request list failed: {list_after_request_status} {list_after_request}")
            require(enrollment_token_ids(list_after_request) == before_token_ids, "approval-gated request unexpectedly minted enrollment tokens")

            transcript = json.dumps([
                preview,
                invalid_preview,
                blocked,
                requested,
                blocked_issue,
                approval_row,
                form_location,
                invalid_form_location,
                list_after_request,
            ], ensure_ascii=False, sort_keys=True)
            require(not leaked_secret(transcript), "Next enrollment request leaked token-like material")

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "policy_route": "/api/mis/agent-gateway/enrollment/policy-preview",
                "request_route": "/api/mis/agent-gateway/enrollment/request",
                "blocked_token_route": "/api/mis/agent-gateway/enrollment/create",
                "blocked_issue_route": "/api/mis/agent-gateway/enrollment/issue-approved",
                "form_route": "/workspace/agents/enrollment-request",
                "preview_status": preview_status,
                "invalid_preview_status": invalid_preview_status,
                "blocked_status": blocked_status,
                "request_status": request_status,
                "blocked_issue_status": blocked_issue_status,
                "form_status": form_status,
                "invalid_form_status": invalid_form_status,
                "request_id": request_id,
                "approval_id": approval_id,
                "task_id": task_id,
                "run_id": run_id,
                "form_request_id": form_request_id,
                "form_approval_id": form_approval_id,
                "token_count_before": len(before_token_ids),
                "token_count_after": len(enrollment_token_ids(list_after_request)),
                "secret_leaked": False,
                "token_issued": False,
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
