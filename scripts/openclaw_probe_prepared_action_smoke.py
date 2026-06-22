#!/usr/bin/env python3
"""Verify OpenClaw fixed probe uses prepared-action exact resume."""
from __future__ import annotations

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
from pathlib import Path
log_path = Path(os.environ["OPENCLAW_FAKE_LOG"])
with log_path.open("a", encoding="utf-8") as handle:
    handle.write("called\\n")
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
        require(bool(prepared_action_id and approval_id and prompt_hash), f"prepare missing ids/hash: {prepare}", failures)
        require(prepare.get("provider_call_performed") is False, f"prepare performed provider call: {prepare}", failures)
        require(prepare.get("raw_prompt_omitted") is True, f"prepare did not omit raw prompt: {prepare}", failures)
        require(call_count(fake_log) == 0, "provider called before approval", failures)

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

        mismatch, mismatch_status = http_json("POST", base_url, "/api/integrations/openclaw/probe", {
            "confirm_run": True,
            "prepared_action_id": prepared_action_id,
            "prompt_hash": "bad-prompt-hash",
        })
        require(mismatch_status == 409 and mismatch.get("error") == "prepared_action_prompt_hash_mismatch", f"mismatch should be blocked: {mismatch_status} {mismatch}", failures)
        require(call_count(fake_log) == 0, "provider called during hash mismatch", failures)

        resumed, resumed_status = http_json("POST", base_url, "/api/integrations/openclaw/probe", {
            "confirm_run": True,
            "prepared_action_id": prepared_action_id,
            "prompt_hash": prompt_hash,
        })
        require(resumed_status == 201 and resumed.get("created") is True and resumed.get("ok") is True, f"resume should call provider once: {resumed_status} {resumed}", failures)
        require(resumed.get("prepared_action_status") == "consumed", f"prepared action not consumed: {resumed}", failures)
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
