#!/usr/bin/env python3
"""Verify Team Governance entitlement gates approval-based enrollment."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def write_entitlements(path: Path, edition: str) -> None:
    path.write_text(
        json.dumps({"edition": edition, "overrides": {}, "notes": "Temporary Team entitlement smoke fixture. No secrets."}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return exc.code, body


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
            status, _payload = http_json("GET", base_url, "/api/commercial/entitlements")
            if status == 200:
                return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def request_payload(run_stamp: str, suffix: str) -> dict:
    return {
        "agent_id": f"agt_team_enroll_{suffix}_{run_stamp}",
        "name": f"Team Enrollment {suffix}",
        "role": "Remote AI Digital Employee",
        "runtime_type": "mock",
        "workspace_id": "local-demo",
        "scopes": ["agents:heartbeat", "tasks:read", "tasks:claim", "runs:write", "audit:write"],
        "reason": f"Team entitlement enrollment smoke {suffix}.",
    }


def assert_no_raw_token(label: str, payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    require("agtok_" not in text and "agtsess_" not in text, f"{label} leaked a raw token: {payload}")


def validate_block(base_url: str, edition: str, run_stamp: str) -> dict:
    status, entitlements = http_json("GET", base_url, "/api/commercial/entitlements")
    require(status == 200, f"{edition} entitlement status failed: {status} {entitlements}")
    require(entitlements.get("edition") == edition, f"edition mismatch for {edition}: {entitlements}")
    gates = {gate.get("capability"): gate for gate in entitlements.get("gates") or [] if isinstance(gate, dict)}
    approval_gate = gates.get("approval_policies") or {}
    require(approval_gate.get("enforcement") == "fail_closed", f"approval_policies should be fail_closed: {approval_gate}")
    require(approval_gate.get("enabled") is False, f"approval_policies should be disabled in {edition}: {approval_gate}")
    status, blocked = http_json("POST", base_url, "/api/agent-gateway/enrollment/request", request_payload(run_stamp, edition))
    require(status == 403, f"{edition} enrollment request should be blocked: {status} {blocked}")
    require(blocked.get("error") == "entitlement_required", f"{edition} wrong block error: {blocked}")
    require(blocked.get("capability") == "approval_policies", f"{edition} wrong capability: {blocked}")
    require(blocked.get("required_edition") == "team_governance", f"{edition} wrong required edition: {blocked}")
    require(blocked.get("current_edition") == edition, f"{edition} wrong current edition: {blocked}")
    require(blocked.get("enforcement") == "fail_closed", f"{edition} wrong enforcement: {blocked}")
    require(blocked.get("billing_call_performed") is False, f"{edition} should not call billing: {blocked}")
    require(blocked.get("live_execution_performed") is False, f"{edition} should not execute live work: {blocked}")
    assert_no_raw_token(f"{edition} blocked request", blocked)
    return {"edition": edition, "status": status, "capability": blocked.get("capability")}


def validate_team_request_issue(base_url: str, run_stamp: str) -> dict:
    status, entitlements = http_json("GET", base_url, "/api/commercial/entitlements")
    require(status == 200 and entitlements.get("edition") == "team_governance", f"team entitlement status failed: {status} {entitlements}")
    gates = {gate.get("capability"): gate for gate in entitlements.get("gates") or [] if isinstance(gate, dict)}
    approval_gate = gates.get("approval_policies") or {}
    require(approval_gate.get("enabled") is True and approval_gate.get("enforcement") == "fail_closed", f"team approval gate mismatch: {approval_gate}")
    status, requested = http_json("POST", base_url, "/api/agent-gateway/enrollment/request", request_payload(run_stamp, "team"))
    require(status == 201, f"team enrollment request failed: {status} {requested}")
    assert_no_raw_token("team request", requested)
    request = requested.get("request") or {}
    approval = requested.get("approval") or {}
    request_id = request.get("request_id")
    approval_id = approval.get("approval_id")
    require(request_id and approval_id, f"team request missing ids: {requested}")

    status, premature = http_json("POST", base_url, "/api/agent-gateway/enrollment/issue-approved", {"approval_id": approval_id})
    require(status == 409 and premature.get("error") == "approval_required", f"premature issue should require approval: {status} {premature}")

    status, approved = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
    require(status == 200 and approved.get("decision") == "approved", f"approval failed: {status} {approved}")

    status, issued = http_json("POST", base_url, "/api/agent-gateway/enrollment/issue-approved", {"approval_id": approval_id, "ttl_days": 1, "heartbeat_timeout_sec": 60})
    require(status == 201, f"team approved issue failed: {status} {issued}")
    token = issued.get("token")
    token_id = issued.get("token_id")
    require(token and token_id, f"team issue missing one-time token: {issued}")
    require(issued.get("issued_from_request_id") == request_id, f"issued request mismatch: {issued}")

    status, heartbeat = http_json("POST", base_url, "/api/agent-gateway/heartbeat", {"status": "idle", "summary": "team entitlement token online"}, token=token)
    require(status == 200, f"team issued token heartbeat failed: {status} {heartbeat}")
    return {
        "request_id": request_id,
        "approval_id": approval_id,
        "token_ref": str(token_id)[-12:],
        "heartbeat_status": heartbeat.get("status"),
    }


def validate_downgrade_issue_block(base_url: str, entitlement_path: Path, run_stamp: str) -> dict:
    write_entitlements(entitlement_path, "team_governance")
    status, requested = http_json("POST", base_url, "/api/agent-gateway/enrollment/request", request_payload(run_stamp, "downgrade"))
    require(status == 201, f"downgrade setup request failed: {status} {requested}")
    approval_id = ((requested.get("approval") or {}).get("approval_id"))
    require(approval_id, f"downgrade setup missing approval: {requested}")
    status, approved = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
    require(status == 200 and approved.get("decision") == "approved", f"downgrade approval failed: {status} {approved}")

    write_entitlements(entitlement_path, "pro_workspace")
    status, blocked = http_json("POST", base_url, "/api/agent-gateway/enrollment/issue-approved", {"approval_id": approval_id})
    require(status == 403, f"downgraded issue should be entitlement-blocked: {status} {blocked}")
    require(blocked.get("capability") == "approval_policies", f"downgrade wrong capability: {blocked}")
    require(blocked.get("current_edition") == "pro_workspace", f"downgrade wrong current edition: {blocked}")
    assert_no_raw_token("downgrade issue block", blocked)
    return {"status": status, "capability": blocked.get("capability"), "current_edition": blocked.get("current_edition")}


def validate_audit(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT entity_id, metadata_json
            FROM audit_logs
            WHERE action='commercial.entitlement_blocked'
            ORDER BY created_at
            """
        ).fetchall()
    approval_blocks = 0
    billing_false = True
    for row in rows:
        if row["entity_id"] == "approval_policies":
            approval_blocks += 1
            metadata = json.loads(row["metadata_json"] or "{}")
            if metadata.get("billing_call_performed") is not False:
                billing_false = False
    require(approval_blocks >= 3, f"expected Free/Pro/downgrade approval_policies audit blocks: {approval_blocks}")
    require(billing_false, "approval_policies audit metadata should prove billing_call_performed=false")
    return {"approval_policies_blocks": approval_blocks, "metadata_billing_call_false": billing_false}


def main() -> int:
    proc: subprocess.Popen[str] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="agentops-team-entitlement-enrollment-") as tmp:
            tmp_path = Path(tmp)
            db_path = tmp_path / "agentops.db"
            entitlement_path = tmp_path / "entitlements.local.json"
            write_entitlements(entitlement_path, "free_local")
            port = free_port()
            base_url = f"http://127.0.0.1:{port}"
            env = os.environ.copy()
            env["AGENTOPS_DB_PATH"] = str(db_path)
            env["AGENTOPS_ENTITLEMENTS_PATH"] = str(entitlement_path)
            env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
            env.pop("AGENTOPS_EDITION", None)
            reset = run([sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset"], env=env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")
            proc = start_server(port, env)
            wait_ready(base_url, proc)
            run_stamp = stamp()
            free_block = validate_block(base_url, "free_local", run_stamp)
            write_entitlements(entitlement_path, "pro_workspace")
            pro_block = validate_block(base_url, "pro_workspace", run_stamp)
            write_entitlements(entitlement_path, "team_governance")
            team_issue = validate_team_request_issue(base_url, run_stamp)
            downgrade_block = validate_downgrade_issue_block(base_url, entitlement_path, run_stamp)
            audit_evidence = validate_audit(db_path)
            output = {
                "ok": True,
                "base_url": base_url,
                "free_block": free_block,
                "pro_block": pro_block,
                "team_issue": team_issue,
                "downgrade_issue_block": downgrade_block,
                "audit_evidence": audit_evidence,
                "token_omitted": True,
            }
            text = json.dumps(output, ensure_ascii=False, sort_keys=True)
            require("agtok_" not in text and "agtsess_" not in text, "smoke output leaked raw token")
            print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
