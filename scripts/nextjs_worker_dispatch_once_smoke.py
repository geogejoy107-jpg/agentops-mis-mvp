#!/usr/bin/env python3
"""Verify Next.js can dispatch one safe mock worker through the MIS proxy."""
from __future__ import annotations

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
CONTRACT_ID = "nextjs_worker_dispatch_once_v1"

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


def worker_run_id(payload: dict[str, Any]) -> str:
    result = ((payload.get("worker_result") or {}).get("results") or [{}])[0] or {}
    return str(result.get("run_id") or "")


def worker_manifest_id(payload: dict[str, Any]) -> str:
    result = ((payload.get("worker_result") or {}).get("results") or [{}])[0] or {}
    return str(result.get("plan_evidence_manifest_id") or "")


def task_ids(payload: Any) -> set[str]:
    if not isinstance(payload, list):
        return set()
    return {str(item.get("task_id") or "") for item in payload if isinstance(item, dict) and item.get("task_id")}


def verify_dispatch_payload(label: str, payload: dict[str, Any]) -> tuple[str, str, str]:
    task_id = str(payload.get("task_id") or "")
    run_id = worker_run_id(payload)
    manifest_id = worker_manifest_id(payload)
    result = ((payload.get("worker_result") or {}).get("results") or [{}])[0] or {}
    require(payload.get("provider") == "agentops-worker", f"{label} wrong provider: {payload}")
    require(payload.get("adapter") == "mock", f"{label} wrong adapter: {payload}")
    require(payload.get("ok") is True, f"{label} worker dispatch did not complete: {payload}")
    require(task_id and run_id, f"{label} missing task/run id: {payload}")
    require(result.get("plan_id"), f"{label} missing agent plan id: {payload}")
    require(manifest_id and result.get("plan_evidence_status") == "verified", f"{label} missing verified plan evidence: {payload}")
    require(result.get("plan_evidence_pass") is True, f"{label} plan evidence did not pass: {payload}")
    return task_id, run_id, manifest_id


def main() -> int:
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "error": "npx is required for Next.js worker dispatch smoke"}, indent=2), file=sys.stderr)
        return 1

    processes: list[subprocess.Popen[str]] = []
    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-worker-dispatch-") as tmp:
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

            proxy_block_before_status, proxy_block_before_payload = http_json_status("GET", f"{api_base}/api/tasks")
            require(proxy_block_before_status == 200, f"pre-proxy-block task list failed: {proxy_block_before_status} {proxy_block_before_payload}")
            proxy_block_before_ids = task_ids(proxy_block_before_payload)
            proxy_block_status, proxy_block_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/workers/local/dispatch-once",
                {
                    "adapter": "hermes",
                    "confirm_run": True,
                    "title": "Blocked Next worker proxy dispatch smoke",
                },
            )
            require(proxy_block_status == 403, f"non-mock Next proxy dispatch did not fail closed: {proxy_block_status} {proxy_block_payload}")
            require(proxy_block_payload.get("error") == "mock_only_next_parity", f"non-mock Next proxy dispatch returned wrong error: {proxy_block_payload}")
            proxy_block_after_status, proxy_block_after_payload = http_json_status("GET", f"{api_base}/api/tasks")
            require(proxy_block_after_status == 200, f"post-proxy-block task list failed: {proxy_block_after_status} {proxy_block_after_payload}")
            require(task_ids(proxy_block_after_payload) == proxy_block_before_ids, "non-mock Next proxy dispatch created or removed tasks")

            proxy_status, proxy_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/workers/local/dispatch-once",
                {
                    "adapter": "mock",
                    "title": "Next worker proxy dispatch smoke",
                    "description": "Verify Next /api/mis can dispatch one safe mock worker.",
                    "acceptance_criteria": "Worker must complete and write plan evidence.",
                },
            )
            require(proxy_status == 201, f"Next proxy worker dispatch returned {proxy_status}: {proxy_payload}")
            proxy_task_id, proxy_run_id, proxy_manifest_id = verify_dispatch_payload("proxy dispatch", proxy_payload)

            next_task_status, next_task_payload = http_json_status("GET", f"{next_base}/api/mis/tasks/{proxy_task_id}")
            require(next_task_status == 200, f"Next task readback failed: {next_task_status} {next_task_payload}")
            require((next_task_payload.get("task") or {}).get("status") == "completed", f"proxy dispatch task not completed: {next_task_payload}")

            blocked_before_status, blocked_before_payload = http_json_status("GET", f"{api_base}/api/tasks")
            require(blocked_before_status == 200, f"pre-block task list failed: {blocked_before_status} {blocked_before_payload}")
            blocked_before_ids = task_ids(blocked_before_payload)
            blocked_status, blocked_location = post_form_no_redirect(f"{next_base}/workspace/agents/dispatch-once", {"adapter": "hermes"})
            require(blocked_status == 303, f"non-mock form fallback did not redirect with 303: {blocked_status} {blocked_location}")
            blocked_query = urllib.parse.parse_qs(urllib.parse.urlparse(blocked_location).query)
            require(blocked_query.get("dispatch_status") == ["failed"], f"non-mock form fallback did not fail closed: {blocked_location}")
            require(blocked_query.get("error") == ["mock_only_next_parity"], f"non-mock form fallback returned wrong error: {blocked_location}")
            require(not blocked_query.get("task_id") and not blocked_query.get("run_id"), f"non-mock form fallback returned task/run ids: {blocked_location}")
            blocked_after_status, blocked_after_payload = http_json_status("GET", f"{api_base}/api/tasks")
            require(blocked_after_status == 200, f"post-block task list failed: {blocked_after_status} {blocked_after_payload}")
            require(task_ids(blocked_after_payload) == blocked_before_ids, "non-mock form fallback created or removed tasks")

            form_status, form_location = post_form_no_redirect(f"{next_base}/workspace/agents/dispatch-once", {"adapter": "mock"})
            require(form_status == 303, f"form fallback did not redirect with 303: {form_status} {form_location}")
            parsed_location = urllib.parse.urlparse(form_location)
            form_query = urllib.parse.parse_qs(parsed_location.query)
            require(form_query.get("dispatch_status") == ["started"], f"form fallback did not report started: {form_location}")
            form_task_id = (form_query.get("task_id") or [""])[0]
            form_run_id = (form_query.get("run_id") or [""])[0]
            require(form_task_id and form_run_id, f"form fallback missing task/run ids: {form_location}")

            direct_status, direct_task_payload = http_json_status("GET", f"{api_base}/api/tasks/{form_task_id}")
            require(direct_status == 200, f"direct form task readback failed: {direct_status} {direct_task_payload}")
            require((direct_task_payload.get("task") or {}).get("status") == "completed", f"form dispatch task not completed: {direct_task_payload}")

            transcript = json.dumps([proxy_block_payload, proxy_payload, next_task_payload, direct_task_payload, blocked_location], ensure_ascii=False, sort_keys=True)
            require(not leaked_secret(transcript), "Next worker dispatch leaked token-like material")

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "proxy_route": "/api/mis/workers/local/dispatch-once",
                "form_route": "/workspace/agents/dispatch-once",
                "non_mock_proxy_status": proxy_block_status,
                "proxy_status": proxy_status,
                "proxy_task_id": proxy_task_id,
                "proxy_run_id": proxy_run_id,
                "proxy_manifest_id": proxy_manifest_id,
                "form_status": form_status,
                "non_mock_form_status": blocked_status,
                "non_mock_form_error": "mock_only_next_parity",
                "form_task_id": form_task_id,
                "form_run_id": form_run_id,
                "task_readback_status": next_task_status,
                "direct_form_readback_status": direct_status,
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
