#!/usr/bin/env python3
"""Verify enrollment request -> approval -> token issue workflow."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return exc.code, body


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(cmd: list[str], *, env: dict[str, str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True, timeout=timeout, check=False)


def start_server(port: int, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout_sec: int = 30) -> None:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            out, _err = proc.communicate(timeout=1)
            raise RuntimeError(f"server exited early: rc={proc.returncode} output={out}")
        try:
            status, payload = http_json("GET", base_url, "/api/commercial/entitlements")
            if status == 200 and payload.get("edition") == "team_governance":
                return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"server did not become ready as team_governance: {last_error}")


def smoke(base_url: str, run_stamp: str) -> dict:
    agent_id = f"agt_enroll_approval_{run_stamp}"
    token_id = None
    status, requested = http_json("POST", base_url, "/api/agent-gateway/enrollment/request", {
        "agent_id": agent_id,
        "name": "Approved Remote Worker",
        "role": "Remote AI Digital Employee",
        "runtime_type": "mock",
        "workspace_id": "local-demo",
        "scopes": ["agents:heartbeat", "tasks:read", "audit:write"],
        "reason": "Smoke test remote enrollment approval workflow.",
    })
    require(status == 201, f"request failed: {status} {requested}")
    require("token" not in requested and "token_id" not in requested, f"request leaked token data: {requested}")
    request = requested.get("request") or {}
    approval = requested.get("approval") or {}
    request_id = request.get("request_id")
    approval_id = approval.get("approval_id")
    task_id = request.get("task_id")
    run_id = request.get("run_id")
    require(request_id and approval_id and task_id and run_id, f"request missing ids: {requested}")

    status, premature = http_json("POST", base_url, "/api/agent-gateway/enrollment/issue-approved", {"approval_id": approval_id})
    require(status == 409, f"premature issue should require approval: {status} {premature}")

    status, approved = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
    require(status == 200, f"approval failed: {status} {approved}")
    require(approved.get("decision") == "approved", f"approval decision missing: {approved}")

    status, issued = http_json("POST", base_url, "/api/agent-gateway/enrollment/issue-approved", {
        "approval_id": approval_id,
        "ttl_days": 1,
        "heartbeat_timeout_sec": 60,
    })
    require(status == 201, f"issue approved failed: {status} {issued}")
    token = issued.get("token")
    token_id = issued.get("token_id")
    require(token and token_id, f"issued response missing one-time token: {issued}")
    require(issued.get("issued_from_request_id") == request_id, f"issued request id mismatch: {issued}")

    status, heartbeat = http_json("POST", base_url, "/api/agent-gateway/heartbeat", {
        "status": "idle",
        "summary": "approved enrollment token online",
    }, token=token)
    require(status == 200, f"issued token heartbeat failed: {status} {heartbeat}")

    return {
        "agent_id": agent_id,
        "request_id": request_id,
        "approval_id": approval_id,
        "task_id": task_id,
        "run_id": run_id,
        "token_id": token_id,
        "premature_issue_status": premature.get("error"),
        "heartbeat_status": heartbeat.get("status"),
        "token_omitted": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify enrollment approval workflow.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL"), help="Existing Team Governance MIS API. Omit to start an isolated team_governance fixture.")
    args = parser.parse_args(argv)
    result = {"ok": False, "base_url": args.base_url}
    token_id = None
    proc: subprocess.Popen[str] | None = None
    tmp_ctx: tempfile.TemporaryDirectory[str] | None = None
    try:
        base_url = args.base_url
        if not base_url:
            tmp_ctx = tempfile.TemporaryDirectory(prefix="agentops-enrollment-approval-")
            tmp = tmp_ctx.name
            port = free_port()
            base_url = f"http://127.0.0.1:{port}"
            env = os.environ.copy()
            env["AGENTOPS_DB_PATH"] = str(Path(tmp) / "agentops.db")
            env["AGENTOPS_EDITION"] = "team_governance"
            env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
            env.pop("AGENTOPS_ENTITLEMENTS_PATH", None)
            reset = run([sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset"], env=env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")
            proc = start_server(port, env)
            wait_ready(base_url, proc)
        result["base_url"] = base_url
        result["fixture_edition"] = "team_governance" if not args.base_url else "external"
        result["smoke"] = smoke(base_url, stamp())
        token_id = (result["smoke"] or {}).pop("token_id", None)
        if token_id:
            result["smoke"]["token_ref"] = str(token_id)[-12:]
        result["ok"] = True
        return 0
    except Exception as exc:
        result["error"] = str(exc)
        return 1
    finally:
        if token_id and result.get("base_url"):
            status, revoked = http_json("POST", str(result["base_url"]), "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})
            result["cleanup"] = {"status": status, "revoked": revoked.get("revoked")}
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        if tmp_ctx:
            tmp_ctx.cleanup()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
