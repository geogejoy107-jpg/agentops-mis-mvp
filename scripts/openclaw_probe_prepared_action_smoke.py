#!/usr/bin/env python3
"""Verify OpenClaw fixed probe uses prepared-action exact resume."""
from __future__ import annotations

import concurrent.futures
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_fake_openclaw(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path
log_path = Path(os.environ["OPENCLAW_FAKE_LOG"])
with log_path.open("a", encoding="utf-8") as handle:
    handle.write("called\\n")
time.sleep(0.25)
print(json.dumps({
    "runId": "fake-openclaw-probe-run",
    "result": {
        "meta": {
            "finalAssistantVisibleText": "OPENCLAW_MIS_PROBE_OK",
            "durationMs": 42,
            "agentMeta": {
                "provider": "openclaw-fake",
                "model": "openclaw-fake-model",
                "usage": {"input": 1, "output": 1}
            }
        },
        "payloads": [{"text": "OPENCLAW_MIS_PROBE_OK"}]
    }
}))
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def call_count(log_path: Path) -> int:
    if not log_path.exists():
        return 0
    return len([line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()])


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
            payload, status = http_json("GET", base_url, "/api/integrations/openclaw/status")
            if status == 200 and payload.get("provider") == "openclaw":
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
    app_port = free_port()
    temp_dir = Path(tempfile.mkdtemp(prefix="agentops-openclaw-prepared-action-"))
    db_path = temp_dir / "agentops.sqlite"
    openclaw_home = temp_dir / "openclaw-home"
    openclaw_home.mkdir(parents=True, exist_ok=True)
    fake_openclaw = temp_dir / "openclaw"
    fake_log = temp_dir / "openclaw.log"
    write_fake_openclaw(fake_openclaw)

    env = os.environ.copy()
    env.update({
        "AGENTOPS_DB_PATH": str(db_path),
        "OPENCLAW_HOME": str(openclaw_home),
        "OPENCLAW_BIN": str(fake_openclaw),
        "OPENCLAW_FAKE_LOG": str(fake_log),
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

        dry, dry_status = http_json("POST", base_url, "/api/integrations/openclaw/probe", {"confirm_run": False})
        require(dry_status == 201 and dry.get("dry_run") is True, f"dry run should remain preview-only: {dry_status} {dry}", failures)
        require(call_count(fake_log) == 0, "provider called during dry-run", failures)

        prepare, prepare_status = http_json("POST", base_url, "/api/integrations/openclaw/probe", {"confirm_run": True})
        require(prepare_status == 202, f"prepare should be 202: {prepare_status} {prepare}", failures)
        prepared_action_id = prepare.get("prepared_action_id")
        approval_id = prepare.get("approval_id")
        prompt_hash = prepare.get("prompt_hash")
        run_id = prepare.get("run_id")
        task_id = prepare.get("task_id")
        require(bool(prepared_action_id and approval_id and prompt_hash and run_id), f"prepare missing ids/hash: {prepare}", failures)
        require(prepare.get("provider_call_performed") is False, f"prepare performed provider call: {prepare}", failures)
        require(prepare.get("raw_prompt_omitted") is True, f"prepare did not omit raw prompt: {prepare}", failures)
        require(call_count(fake_log) == 0, "provider called before approval", failures)

        secondary_prepare, secondary_prepare_status = http_json("POST", base_url, "/api/integrations/openclaw/probe", {
            "confirm_run": True,
            "workspace_id": "ws_openclaw_secondary",
        })
        require(secondary_prepare_status == 202, f"secondary workspace prepare failed: {secondary_prepare_status} {secondary_prepare}", failures)
        require(
            secondary_prepare.get("task_id") != task_id
            and secondary_prepare.get("run_id") != run_id
            and secondary_prepare.get("prepared_action_id") != prepared_action_id,
            f"secondary workspace reused fixed-runtime identifiers: {secondary_prepare}",
            failures,
        )
        task_rebind, task_rebind_status = http_json("POST", base_url, "/api/integrations/openclaw/probe", {
            "confirm_run": True,
            "workspace_id": "ws_openclaw_secondary",
            "task_id": task_id,
        })
        require(
            task_rebind_status == 400 and task_rebind.get("error") == "server_generated_runtime_identifiers_required",
            f"caller-controlled task id was accepted during prepare: {task_rebind_status} {task_rebind}",
            failures,
        )
        require(call_count(fake_log) == 0, "provider called during workspace-id isolation checks", failures)

        premature, premature_status = http_json("POST", base_url, "/api/integrations/openclaw/probe", {
            "confirm_run": True,
            "prepared_action_id": prepared_action_id,
            "prompt_hash": prompt_hash,
        })
        require(premature_status == 428 and premature.get("error") == "approval_required", f"premature resume should require approval: {premature_status} {premature}", failures)
        require(call_count(fake_log) == 0, "provider called during premature resume", failures)

        approved, approved_status = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
        require(approved_status == 200 and approved.get("decision") == "approved", f"approval failed: {approved_status} {approved}", failures)
        require(call_count(fake_log) == 0, "provider called during approval", failures)

        rebound, rebound_status = http_json("POST", base_url, "/api/integrations/openclaw/probe", {
            "confirm_run": True,
            "workspace_id": "ws_openclaw_rebind_attack",
            "task_id": "tsk_openclaw_rebind_attack",
            "run_id": "run_openclaw_rebind_attack",
            "tool_call_id": "tc_openclaw_rebind_attack",
            "approval_id": approval_id,
        })
        require(
            rebound_status == 400 and rebound.get("error") == "server_generated_runtime_identifiers_required",
            f"caller-controlled approval id was accepted through prepare: {rebound_status} {rebound}",
            failures,
        )
        repeated_approval, repeated_approval_status = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
        require(
            repeated_approval_status == 200 and repeated_approval.get("decision") == "approved",
            f"original approval changed after rebind attempt: {repeated_approval_status} {repeated_approval}",
            failures,
        )
        require(call_count(fake_log) == 0, "provider called during approval rebind attempt", failures)

        prepared_rebind, prepared_rebind_status = http_json("POST", base_url, "/api/integrations/openclaw/probe", {
            "confirm_run": True,
            "workspace_id": "ws_openclaw_prepared_rebind_attack",
            "task_id": "tsk_openclaw_prepared_rebind_attack",
            "run_id": run_id,
            "tool_call_id": "tc_openclaw_prepared_rebind_attack",
            "approval_id": "ap_openclaw_prepared_rebind_attack",
        })
        require(
            prepared_rebind_status == 400 and prepared_rebind.get("error") == "server_generated_runtime_identifiers_required",
            f"caller-controlled run/tool/approval ids were accepted: {prepared_rebind_status} {prepared_rebind}",
            failures,
        )
        require(call_count(fake_log) == 0, "provider called during prepared-action rebind attempt", failures)

        cross_workspace, cross_workspace_status = http_json("POST", base_url, "/api/integrations/openclaw/probe", {
            "confirm_run": True,
            "workspace_id": "ws_openclaw_rebind_attack",
            "prepared_action_id": prepared_action_id,
            "prompt_hash": prompt_hash,
        })
        require(
            cross_workspace_status == 404 and cross_workspace.get("error") == "prepared_action_not_found",
            f"cross-workspace prepared action was visible: {cross_workspace_status} {cross_workspace}",
            failures,
        )
        require(call_count(fake_log) == 0, "provider called during cross-workspace prepared-action lookup", failures)

        mismatch, mismatch_status = http_json("POST", base_url, "/api/integrations/openclaw/probe", {
            "confirm_run": True,
            "prepared_action_id": prepared_action_id,
            "prompt_hash": "bad-prompt-hash",
        })
        require(mismatch_status == 409 and mismatch.get("error") == "prepared_action_prompt_hash_mismatch", f"mismatch should be blocked: {mismatch_status} {mismatch}", failures)
        require(call_count(fake_log) == 0, "provider called during hash mismatch", failures)

        resume_body = {
            "confirm_run": True,
            "prepared_action_id": prepared_action_id,
            "prompt_hash": prompt_hash,
        }
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            resume_results = list(pool.map(
                lambda _index: http_json("POST", base_url, "/api/integrations/openclaw/probe", resume_body),
                range(2),
            ))
        require(sorted(status for _payload, status in resume_results) == [201, 409], f"concurrent resumes were not single-winner: {resume_results}", failures)
        resumed, resumed_status = next((item for item in resume_results if item[1] == 201), ({}, 0))
        loser, loser_status = next((item for item in resume_results if item[1] == 409), ({}, 0))
        require(resumed_status == 201 and resumed.get("created") is True and resumed.get("ok") is True, f"resume should call provider once: {resumed_status} {resumed}", failures)
        require(resumed.get("prepared_action_status") == "consumed", f"prepared action not consumed: {resumed}", failures)
        require(loser_status == 409 and loser.get("error") in {"prepared_action_execution_in_progress", "prepared_action_already_consumed"}, f"concurrent loser was not blocked: {loser_status} {loser}", failures)
        require(call_count(fake_log) == 1, "provider should be called exactly once", failures)

        replay, replay_status = http_json("POST", base_url, "/api/integrations/openclaw/probe", {
            "confirm_run": True,
            "prepared_action_id": prepared_action_id,
            "prompt_hash": prompt_hash,
        })
        require(replay_status == 409 and replay.get("error") == "prepared_action_already_consumed", f"replay should be blocked: {replay_status} {replay}", failures)
        require(call_count(fake_log) == 1, "provider called during replay", failures)

        print(json.dumps({
            "ok": not failures,
            "failures": failures,
            "prepared_action_id": prepared_action_id,
            "approval_id": approval_id,
            "approval_rebind_rejected": rebound_status == 400,
            "prepared_action_rebind_rejected": prepared_rebind_status == 400,
            "caller_runtime_identifiers_rejected": all(status == 400 for status in (task_rebind_status, rebound_status, prepared_rebind_status)),
            "cross_workspace_prepared_action_hidden": cross_workspace_status == 404,
            "cross_workspace_prepare_ids_isolated": secondary_prepare_status == 202,
            "cross_workspace_task_rebind_rejected": task_rebind_status == 400,
            "concurrent_resume_single_winner": sorted(status for _payload, status in resume_results) == [201, 409],
            "provider_call_count": call_count(fake_log),
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


if __name__ == "__main__":
    raise SystemExit(main())
