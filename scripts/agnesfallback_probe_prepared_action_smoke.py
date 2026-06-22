#!/usr/bin/env python3
"""Verify Agnesfallback CLI/API fixed probes use prepared-action exact resume."""
from __future__ import annotations

import json
import os
import socket
import stat
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


class FakeAgnesApiHandler(BaseHTTPRequestHandler):
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
        body = json.dumps({
            "id": "fake-agnesfallback-api-probe",
            "choices": [{"message": {"content": "HERMES_AGNES_API_OK"}}],
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


def write_fake_cli(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import os
from pathlib import Path
log_path = Path(os.environ["AGNESFALLBACK_FAKE_LOG"])
with log_path.open("a", encoding="utf-8") as handle:
    handle.write("called\\n")
print("AGNESFALLBACK_OK")
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def cli_call_count(log_path: Path) -> int:
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


def exercise_prepared_probe(
    base_url: str,
    path: str,
    label: str,
    call_count,
    failures: list[str],
) -> dict:
    dry, dry_status = http_json("POST", base_url, path, {"confirm_run": False})
    require(dry_status == 201 and dry.get("dry_run") is True, f"{label} dry run should remain preview-only: {dry_status} {dry}", failures)
    require(call_count() == 0, f"{label} provider called during dry-run", failures)

    prepare, prepare_status = http_json("POST", base_url, path, {"confirm_run": True})
    require(prepare_status == 202, f"{label} prepare should be 202: {prepare_status} {prepare}", failures)
    prepared_action_id = prepare.get("prepared_action_id")
    approval_id = prepare.get("approval_id")
    prompt_hash = prepare.get("prompt_hash")
    require(bool(prepared_action_id and approval_id and prompt_hash), f"{label} prepare missing ids/hash: {prepare}", failures)
    require(prepare.get("provider_call_performed") is False, f"{label} prepare performed provider call: {prepare}", failures)
    require(prepare.get("raw_prompt_omitted") is True, f"{label} prepare did not omit raw prompt: {prepare}", failures)
    require(call_count() == 0, f"{label} provider called before approval", failures)

    premature, premature_status = http_json("POST", base_url, path, {
        "confirm_run": True,
        "prepared_action_id": prepared_action_id,
        "prompt_hash": prompt_hash,
    })
    require(premature_status == 428 and premature.get("error") == "approval_required", f"{label} premature resume should require approval: {premature_status} {premature}", failures)
    require(call_count() == 0, f"{label} provider called during premature resume", failures)

    approved, approved_status = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
    require(approved_status == 200 and approved.get("decision") == "approved", f"{label} approval failed: {approved_status} {approved}", failures)
    require(call_count() == 0, f"{label} provider called during approval", failures)

    mismatch, mismatch_status = http_json("POST", base_url, path, {
        "confirm_run": True,
        "prepared_action_id": prepared_action_id,
        "prompt_hash": "bad-prompt-hash",
    })
    require(mismatch_status == 409 and mismatch.get("error") == "prepared_action_prompt_hash_mismatch", f"{label} mismatch should be blocked: {mismatch_status} {mismatch}", failures)
    require(call_count() == 0, f"{label} provider called during hash mismatch", failures)

    resumed, resumed_status = http_json("POST", base_url, path, {
        "confirm_run": True,
        "prepared_action_id": prepared_action_id,
        "prompt_hash": prompt_hash,
    })
    require(resumed_status == 201 and resumed.get("created") is True and resumed.get("ok") is True, f"{label} resume should call provider once: {resumed_status} {resumed}", failures)
    require(resumed.get("prepared_action_status") == "consumed", f"{label} prepared action not consumed: {resumed}", failures)
    require(call_count() == 1, f"{label} provider should be called exactly once", failures)

    replay, replay_status = http_json("POST", base_url, path, {
        "confirm_run": True,
        "prepared_action_id": prepared_action_id,
        "prompt_hash": prompt_hash,
    })
    require(replay_status == 409 and replay.get("error") == "prepared_action_already_consumed", f"{label} replay should be blocked: {replay_status} {replay}", failures)
    require(call_count() == 1, f"{label} provider called during replay", failures)
    return {
        "prepared_action_id": prepared_action_id,
        "approval_id": approval_id,
        "provider_call_count": call_count(),
    }


def main() -> int:
    failures: list[str] = []
    fake_port = free_port()
    app_port = free_port()
    fake_api = ThreadingHTTPServer(("127.0.0.1", fake_port), FakeAgnesApiHandler)
    fake_thread = threading.Thread(target=fake_api.serve_forever, daemon=True)
    fake_thread.start()

    temp_dir = Path(tempfile.mkdtemp(prefix="agentops-agnes-prepared-action-"))
    db_path = temp_dir / "agentops.sqlite"
    fake_cli = temp_dir / "agnesfallback"
    fake_cli_log = temp_dir / "agnesfallback-cli.log"
    write_fake_cli(fake_cli)
    env = os.environ.copy()
    env.update({
        "AGENTOPS_DB_PATH": str(db_path),
        "HERMES_ALLOW_REAL_RUN": "true",
        "HERMES_REQUIRE_CONFIRM_RUN": "true",
        "AGNESFALLBACK_BIN": str(fake_cli),
        "AGNESFALLBACK_FAKE_LOG": str(fake_cli_log),
        "AGNESFALLBACK_GATEWAY_URL": f"http://127.0.0.1:{fake_port}",
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
        cli = exercise_prepared_probe(
            base_url,
            "/api/integrations/hermes/cli-probe",
            "agnesfallback-cli",
            lambda: cli_call_count(fake_cli_log),
            failures,
        )
        api = exercise_prepared_probe(
            base_url,
            "/api/integrations/hermes/chat-completion-probe",
            "agnesfallback-api",
            lambda: len(FakeAgnesApiHandler.calls),
            failures,
        )
        print(json.dumps({
            "ok": not failures,
            "failures": failures,
            "cli": cli,
            "api": api,
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
        fake_api.shutdown()
        fake_api.server_close()
        for path in sorted(temp_dir.glob("*")):
            try:
                path.unlink()
            except OSError:
                pass
        try:
            temp_dir.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
