#!/usr/bin/env python3
"""Verify Next.js Pixel Office exposes the owner dispatch workflow and form fallbacks."""
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
CONTRACT_ID = "nextjs_pixel_office_dispatch_v1"
SECRET_MARKERS = ["Authorization: " + "Bearer", "agtok" + "_", "agtsess" + "_", "sk" + "-", "ntn" + "_"]
HTML_SECRET_MARKERS = ["Authorization: " + "Bearer", "agtok" + "_", "agtsess" + "_", "ntn" + "_"]

sys.path.insert(0, str(SCRIPTS))

from nextjs_playwright_snapshot_smoke import (  # noqa: E402
    free_port,
    leaked_secret,
    restore_next_env,
    run,
    start_process,
    wait_http,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret_marker(text: str, markers: list[str] = SECRET_MARKERS) -> str | None:
    return next((marker for marker in markers if marker in text), None)


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


def http_text_status(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=90) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def post_form_no_redirect(url: str, payload: dict[str, str | list[str]]) -> tuple[int, str]:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
            return None

    data = urllib.parse.urlencode(payload, doseq=True).encode("utf-8")
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


def query(location: str) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(urllib.parse.urlparse(location).query)


def absolute_location(next_base: str, location: str) -> str:
    parsed = urllib.parse.urlparse(location)
    if parsed.scheme and parsed.path.startswith("/workspace"):
        suffix = parsed.path
        if parsed.query:
            suffix = f"{suffix}?{parsed.query}"
        return f"{next_base}{suffix}"
    if location.startswith("http://") or location.startswith("https://"):
        return location
    return f"{next_base}{location}"


def stop_processes(processes: list[subprocess.Popen[str]]) -> list[str]:
    logs: list[str] = []
    for proc in reversed(processes):
        if proc.poll() is None:
            proc.terminate()
        try:
            output, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate(timeout=5)
        if output:
            logs.append(output[-2000:])
    return logs


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
        with tempfile.TemporaryDirectory(prefix="agentops-next-pixel-dispatch-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            reset_env = os.environ.copy()
            reset_env.pop("AGENTOPS_API_KEY", None)
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset_env["AGENTOPS_EDITION"] = "pro_workspace"
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = os.environ.copy()
            api_env.pop("AGENTOPS_API_KEY", None)
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_env["AGENTOPS_EDITION"] = "pro_workspace"
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env.pop("AGENTOPS_API_KEY", None)
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace/pixel-office")

            pixel_status, pixel_html = http_text_status(f"{next_base}/workspace/pixel-office")
            require(pixel_status == 200, f"Pixel Office page failed: {pixel_status}")
            for text in [
                "Owner dispatch workflow",
                "template intake /workspace/dispatch",
                "worker dispatch /workspace/dispatch/customer-worker",
                "delivery reports /workspace/reports",
            ]:
                require(text in pixel_html, f"Pixel Office owner workflow missing {text!r}")

            dispatch_status, dispatch_html = http_text_status(f"{next_base}/workspace/dispatch")
            require(dispatch_status == 200, f"Dispatch page failed: {dispatch_status}")
            for text in [
                "Owner task composer",
                "/workspace/dispatch/customer-task",
                "/workspace/dispatch/template-job",
                "team selection forwarded",
            ]:
                require(text in dispatch_html, f"Dispatch owner composer missing {text!r}")

            task_status, task_location = post_form_no_redirect(
                f"{next_base}/workspace/dispatch/customer-task",
                {
                    "template_id": "tpl_customer_kb_qa_bot",
                    "owner_agent_id": "agt_cos",
                    "selected_agent_ids": ["agt_cos", "agt_research"],
                    "priority": "high",
                    "risk_level": "medium",
                    "title": "Next owner task dry-run smoke",
                    "description": "Verify Next owner task composer writes a safe planned task.",
                    "acceptance_criteria": "Task must be readable through the Next proxy without raw prompt leakage.",
                    "confirm_run": "false",
                },
            )
            transcripts.append(task_location)
            require(task_status == 303, f"customer-task form did not redirect: {task_status} {task_location}")
            task_query = query(task_location)
            require(task_query.get("customer_task_status") == ["dry_run"], f"customer-task form did not report dry-run: {task_location}")
            task_id = (task_query.get("customer_task_id") or [""])[0]
            require(task_id, f"customer-task form did not return task id: {task_location}")

            task_read_status, task_payload = http_json_status("GET", f"{next_base}/api/mis/tasks/{urllib.parse.quote(task_id)}")
            transcripts.append(task_payload)
            require(task_read_status == 200, f"customer task readback failed: {task_read_status} {task_payload}")
            task = task_payload.get("task") or {}
            require(task.get("task_id") == task_id and task.get("status") == "planned", f"customer task readback wrong: {task_payload}")
            require(task.get("risk_level") == "medium" and task.get("priority") == "high", f"customer task priority/risk not forwarded: {task}")

            job_status, job_location = post_form_no_redirect(
                f"{next_base}/workspace/dispatch/template-job",
                {
                    "template_id": "tpl_customer_kb_qa_bot",
                    "adapter": "mock",
                    "owner_agent_id": "agt_cos",
                    "selected_agent_ids": ["agt_cos", "agt_research"],
                    "priority": "high",
                    "risk_level": "medium",
                    "title": "Next template async job smoke",
                    "description": "Verify Next template async job form submits through the MIS workflow job API.",
                    "acceptance_criteria": "Workflow job must be visible through the Next proxy.",
                    "confirm_run": "true",
                },
            )
            transcripts.append(job_location)
            require(job_status == 303, f"template-job form did not redirect: {job_status} {job_location}")
            job_query = query(job_location)
            require(job_query.get("template_job_status") == ["submitted"], f"template-job form did not report submitted: {job_location}")
            job_id = (job_query.get("template_job_id") or [""])[0]
            require(job_id, f"template-job form did not return job id: {job_location}")

            job_read_status, job_payload = http_json_status("GET", f"{next_base}/api/mis/workflows/jobs/{urllib.parse.quote(job_id)}")
            transcripts.append(job_payload)
            require(job_read_status == 200, f"template job readback failed: {job_read_status} {job_payload}")
            job = job_payload.get("job") or job_payload
            require(job.get("job_id") == job_id, f"template job readback id mismatch: {job_payload}")
            require(job.get("workflow_type") == "customer_task_template", f"template job workflow mismatch: {job_payload}")
            require(job.get("raw_request_omitted") is True, f"template job raw request omission missing: {job_payload}")

            feedback_status, feedback_html = http_text_status(absolute_location(next_base, task_location))
            require(
                feedback_status == 200 and "Owner task dry-run recorded" in feedback_html,
                f"customer task feedback page missing: {feedback_status} body={feedback_html[:500]}",
            )
            feedback_status, feedback_html = http_text_status(absolute_location(next_base, job_location))
            require(
                feedback_status == 200 and "Template async job submitted" in feedback_html,
                f"template job feedback page missing: {feedback_status} body={feedback_html[:500]}",
            )

            transcript_text = json.dumps(transcripts, ensure_ascii=False, sort_keys=True)
            transcript_marker = leaked_secret_marker(transcript_text)
            require(not transcript_marker and not leaked_secret(transcript_text), f"Next Pixel Office dispatch smoke leaked API token-like material marker={transcript_marker}")
            html_text = json.dumps({"pixel": pixel_html, "dispatch": dispatch_html}, ensure_ascii=False, sort_keys=True)
            html_marker = leaked_secret_marker(html_text, HTML_SECRET_MARKERS)
            require(not html_marker, f"Next Pixel Office dispatch page leaked token/session material marker={html_marker}")

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "pixel_route": "/workspace/pixel-office",
                "dispatch_route": "/workspace/dispatch",
                "customer_task_form_route": "/workspace/dispatch/customer-task",
                "template_job_form_route": "/workspace/dispatch/template-job",
                "customer_task_id": task_id,
                "template_job_id": job_id,
                "edition": "pro_workspace",
                "owner_dispatch_workflow": True,
                "team_selection_forwarded": True,
                "secret_leaked": False,
                "token_omitted": True,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        logs = stop_processes(processes)
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": str(exc), "process_logs": logs}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        stop_processes(processes)
        run(["bash", "-lc", f"lsof -tiTCP:{next_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["bash", "-lc", f"lsof -tiTCP:{api_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["rm", "-rf", str(NEXT_APP / ".next")], timeout=10)
        restore_next_env()


if __name__ == "__main__":
    raise SystemExit(main())
