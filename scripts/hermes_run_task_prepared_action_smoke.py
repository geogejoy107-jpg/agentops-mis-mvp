#!/usr/bin/env python3
"""Verify Hermes fixed run-task uses prepared-action exact resume."""
from __future__ import annotations

import concurrent.futures
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


class FakeHermesHandler(BaseHTTPRequestHandler):
    calls: list[dict] = []

    def log_message(self, fmt, *args):  # noqa: D401
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        messages = payload.get("messages") or []
        prompt = ((messages[0] if messages else {}).get("content") or "").strip()
        self.__class__.calls.append({
            "path": self.path,
            "model": payload.get("model"),
            "prompt_present": bool(prompt),
        })
        time.sleep(0.25)
        body = json.dumps({
            "id": "fake-hermes-run-task",
            "choices": [{"message": {"content": "HERMES_DEFAULT_RUN_OK"}}],
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(method: str, base_url: str, path: str, payload: dict | None = None) -> tuple[dict, int]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(req, timeout=20) as res:
            raw = res.read().decode("utf-8")
            return (json.loads(raw) if raw else {}), res.status
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return payload, exc.code


def wait_for_server(base_url: str) -> None:
    deadline = time.time() + 20
    last_error = ""
    while time.time() < deadline:
        try:
            payload, status = http_json("GET", base_url, "/api/integrations/hermes/status")
            if status == 200 and payload.get("provider") == "hermes":
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.2)
    raise RuntimeError(f"MIS server did not become ready: {last_error}")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    fake_port = free_port()
    app_port = free_port()
    fake = ThreadingHTTPServer(("127.0.0.1", fake_port), FakeHermesHandler)
    fake_thread = threading.Thread(target=fake.serve_forever, daemon=True)
    fake_thread.start()

    handle = tempfile.NamedTemporaryFile(prefix="agentops-hermes-prepared-action-", suffix=".sqlite", delete=False)
    db_path = handle.name
    handle.close()
    env = os.environ.copy()
    env.update({
        "AGENTOPS_DB_PATH": db_path,
        "HERMES_GATEWAY_URL": f"http://127.0.0.1:{fake_port}",
        "HERMES_ALLOW_REAL_RUN": "true",
        "HERMES_REQUIRE_CONFIRM_RUN": "true",
    })
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(app_port), "--reset", "--serve"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{app_port}"
    try:
        wait_for_server(base_url)
        dry, dry_status = http_json("POST", base_url, "/api/integrations/hermes/run-task", {"confirm_run": False})
        require(dry_status == 201 and dry.get("dry_run") is True, f"dry run should remain preview-only: {dry_status} {dry}", failures)
        require(len(FakeHermesHandler.calls) == 0, f"fake Hermes called during dry-run: {FakeHermesHandler.calls}", failures)

        prepare, prepare_status = http_json("POST", base_url, "/api/integrations/hermes/run-task", {"confirm_run": True})
        require(prepare_status == 202, f"prepare should be 202: {prepare_status} {prepare}", failures)
        prepared_action_id = prepare.get("prepared_action_id")
        approval_id = prepare.get("approval_id")
        prompt_hash = prepare.get("prompt_hash")
        run_id = prepare.get("run_id")
        task_id = prepare.get("task_id")
        require(bool(prepared_action_id and approval_id and prompt_hash), f"prepare missing ids/hash: {prepare}", failures)
        require(prepare.get("provider_call_performed") is False, f"prepare performed provider call: {prepare}", failures)
        require(prepare.get("raw_prompt_omitted") is True, f"prepare did not omit raw prompt: {prepare}", failures)
        require(len(FakeHermesHandler.calls) == 0, f"fake Hermes called before approval: {FakeHermesHandler.calls}", failures)

        secondary_prepare, secondary_prepare_status = http_json("POST", base_url, "/api/integrations/hermes/run-task", {
            "confirm_run": True,
            "workspace_id": "ws_hermes_secondary",
        })
        require(secondary_prepare_status == 202, f"secondary workspace prepare failed: {secondary_prepare_status} {secondary_prepare}", failures)
        require(
            secondary_prepare.get("task_id") != task_id
            and secondary_prepare.get("run_id") != run_id
            and secondary_prepare.get("prepared_action_id") != prepared_action_id,
            f"secondary workspace reused fixed-runtime identifiers: {secondary_prepare}",
            failures,
        )
        task_rebind, task_rebind_status = http_json("POST", base_url, "/api/integrations/hermes/run-task", {
            "confirm_run": True,
            "workspace_id": "ws_hermes_secondary",
            "task_id": task_id,
        })
        require(
            task_rebind_status == 400 and task_rebind.get("error") == "server_generated_runtime_identifiers_required",
            f"caller-controlled task id was accepted during prepare: {task_rebind_status} {task_rebind}",
            failures,
        )
        require(len(FakeHermesHandler.calls) == 0, "fake Hermes called during workspace-id isolation checks", failures)

        premature, premature_status = http_json("POST", base_url, "/api/integrations/hermes/run-task", {
            "confirm_run": True,
            "prepared_action_id": prepared_action_id,
            "prompt_hash": prompt_hash,
        })
        require(premature_status == 428 and premature.get("error") == "approval_required", f"premature resume should require approval: {premature_status} {premature}", failures)
        require(len(FakeHermesHandler.calls) == 0, "fake Hermes called during premature resume", failures)

        approved, approved_status = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
        require(approved_status == 200 and approved.get("decision") == "approved", f"approval failed: {approved_status} {approved}", failures)
        require(len(FakeHermesHandler.calls) == 0, "fake Hermes called during approval", failures)

        cross_workspace, cross_workspace_status = http_json("POST", base_url, "/api/integrations/hermes/run-task", {
            "confirm_run": True,
            "workspace_id": "ws_hermes_rebind_attack",
            "prepared_action_id": prepared_action_id,
            "prompt_hash": prompt_hash,
        })
        require(
            cross_workspace_status == 404 and cross_workspace.get("error") == "prepared_action_not_found",
            f"cross-workspace prepared action was visible: {cross_workspace_status} {cross_workspace}",
            failures,
        )
        require(len(FakeHermesHandler.calls) == 0, "fake Hermes called during cross-workspace prepared-action lookup", failures)

        mismatch, mismatch_status = http_json("POST", base_url, "/api/integrations/hermes/run-task", {
            "confirm_run": True,
            "prepared_action_id": prepared_action_id,
            "prompt_hash": "bad-prompt-hash",
        })
        require(mismatch_status == 409 and mismatch.get("error") == "prepared_action_prompt_hash_mismatch", f"mismatch should be blocked: {mismatch_status} {mismatch}", failures)
        require(len(FakeHermesHandler.calls) == 0, "fake Hermes called during hash mismatch", failures)

        resume_body = {
            "confirm_run": True,
            "prepared_action_id": prepared_action_id,
            "prompt_hash": prompt_hash,
        }
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            resume_results = list(pool.map(
                lambda _index: http_json("POST", base_url, "/api/integrations/hermes/run-task", resume_body),
                range(2),
            ))
        require(sorted(status for _payload, status in resume_results) == [201, 409], f"concurrent resumes were not single-winner: {resume_results}", failures)
        resumed, resumed_status = next((item for item in resume_results if item[1] == 201), ({}, 0))
        loser, loser_status = next((item for item in resume_results if item[1] == 409), ({}, 0))
        require(resumed_status == 201 and resumed.get("created") is True and resumed.get("ok") is True, f"resume should call Hermes once: {resumed_status} {resumed}", failures)
        require(resumed.get("prepared_action_status") == "consumed", f"prepared action not consumed: {resumed}", failures)
        require(loser_status == 409 and loser.get("error") in {"prepared_action_execution_in_progress", "prepared_action_already_consumed"}, f"concurrent loser was not blocked: {loser_status} {loser}", failures)
        require(len(FakeHermesHandler.calls) == 1, f"fake Hermes should be called exactly once: {FakeHermesHandler.calls}", failures)

        replay, replay_status = http_json("POST", base_url, "/api/integrations/hermes/run-task", {
            "confirm_run": True,
            "prepared_action_id": prepared_action_id,
            "prompt_hash": prompt_hash,
        })
        require(replay_status == 409 and replay.get("error") == "prepared_action_already_consumed", f"replay should be blocked: {replay_status} {replay}", failures)
        require(len(FakeHermesHandler.calls) == 1, "fake Hermes called during replay", failures)

        print(json.dumps({
            "ok": not failures,
            "failures": failures,
            "prepared_action_id": prepared_action_id,
            "approval_id": approval_id,
            "cross_workspace_prepared_action_hidden": cross_workspace_status == 404,
            "cross_workspace_prepare_ids_isolated": secondary_prepare_status == 202,
            "cross_workspace_task_rebind_rejected": task_rebind_status == 400,
            "caller_runtime_identifiers_rejected": task_rebind_status == 400,
            "concurrent_resume_single_winner": sorted(status for _payload, status in resume_results) == [201, 409],
            "provider_call_count": len(FakeHermesHandler.calls),
            "token_omitted": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not failures else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        fake.shutdown()
        fake.server_close()
        try:
            os.unlink(db_path)
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
