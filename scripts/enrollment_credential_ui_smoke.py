#!/usr/bin/env python3
"""Verify issued Agent Gateway credentials are one-time UI secrets."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AI_EMPLOYEES = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "AIEmployees.tsx"
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"
SERVER = ROOT / "server.py"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def extract_block(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start)
    if end < 0:
        return text[start:]
    return text[start:end]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(method: str, base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw), raw
        except Exception:
            return exc.code, {"raw": raw}, raw


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _payload, _raw = http_json("GET", base_url, "/api/local/readiness")
            if status == 200:
                return
        except urllib.error.URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def secret_leaked(text: str, extra_secrets: list[str] | None = None) -> bool:
    extra = extra_secrets or []
    return any(pattern.search(text) for pattern in SECRET_PATTERNS) or any(secret and secret in text for secret in extra)


def api_contract_smoke(failures: list[str]) -> dict:
    with tempfile.TemporaryDirectory(prefix="agentops-enrollment-credential-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["HERMES_ALLOW_REAL_RUN"] = "false"
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        token_id = ""
        raw_token = ""
        try:
            wait_ready(base_url, proc)
            status, created, create_raw = http_json("POST", base_url, "/api/agent-gateway/enrollment/create", {
                "agent_id": "agt_credential_ui_smoke",
                "name": "Credential UI Smoke",
                "runtime_type": "mock",
                "scopes": ["agents:heartbeat", "tasks:read", "audit:write"],
                "ttl_days": 1,
                "heartbeat_timeout_sec": 60,
            })
            require(status == 201, f"enrollment create failed: {status} {created}", failures)
            raw_token = str(created.get("token") or "")
            token_id = str(created.get("token_id") or "")
            require(bool(raw_token and token_id), f"create should return one-time token and token id: {created}", failures)

            status, listed, list_raw = http_json("GET", base_url, "/api/agent-gateway/enrollments")
            require(status == 200, f"enrollment list failed: {status} {listed}", failures)
            require(listed.get("token_omitted") is True, f"list token_omitted missing: {listed}", failures)
            enrollments = listed.get("enrollments") or []
            listed_row = next((item for item in enrollments if item.get("token_id") == token_id), {})
            require(bool(listed_row), f"created token id missing from list: {listed}", failures)
            require("token" not in listed_row, f"list row exposed raw token field: {listed_row}", failures)
            require("token_hash" not in listed_row, f"list row exposed token_hash field: {listed_row}", failures)
            require(not secret_leaked(list_raw, [raw_token]), "list response leaked a raw token-like value", failures)
            redacted_create_raw = create_raw.replace(raw_token, "<redacted-token>") if raw_token else create_raw
            require(not secret_leaked(redacted_create_raw, []), "create response leaked unrelated token-like material", failures)

            return {
                "base_url": base_url,
                "token_id": token_id,
                "list_token_omitted": listed.get("token_omitted") is True,
                "raw_token_absent_from_list": not secret_leaked(list_raw, [raw_token]),
                "temp_db": True,
            }
        finally:
            if token_id:
                http_json("POST", base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def main() -> int:
    failures: list[str] = []
    ai = AI_EMPLOYEES.read_text(encoding="utf-8")
    live_api = LIVE_API.read_text(encoding="utf-8")
    server = SERVER.read_text(encoding="utf-8")

    enrollment_interface = extract_block(
        live_api,
        "export interface AgentGatewayEnrollment {",
        "export interface AgentGatewayEnrollmentListPayload",
    )
    enrollment_list_loader = extract_block(
        live_api,
        "export async function loadAgentGatewayEnrollments",
        "export async function loadAgentGatewaySessions",
    )
    enrollment_create_result = extract_block(
        live_api,
        "export interface AgentGatewayEnrollmentCreateResult",
        "export interface AgentGatewayEnrollmentRequestResult",
    )
    list_route = extract_block(
        server,
        'if path == "/api/agent-gateway/enrollments":',
        'if path == "/api/agent-gateway/sessions":',
    )
    one_time_card = extract_block(
        ai,
        'data-testid="one-time-issued-credential"',
        '<div className="mt-4">',
    )
    copy_helper = extract_block(
        ai,
        "const copyIssuedCredential = async () => {",
        "const panelLoadState",
    )
    recent_enrollments = extract_block(
        ai,
        "{copy.recentEnrollments}",
        "{copy.recentSessions}",
    )

    require("token: string;" not in enrollment_interface, "enrollment list item type must not expose token", failures)
    require("token_hash" not in enrollment_interface, "enrollment list item type must not expose token_hash", failures)
    require("token: string;" in enrollment_create_result, "create result should still expose one-time token", failures)
    require("token_omitted: boolean;" in live_api, "enrollment list payload should expose token_omitted proof", failures)
    require("token_omitted: boolValue(raw.token_omitted)" in enrollment_list_loader, "list loader should preserve token_omitted", failures)
    require('"token_omitted": True' in list_route, "enrollment list route should return token_omitted true", failures)
    require("token_hash" not in list_route, "enrollment list route must not query or return token_hash", failures)
    require("navigator.clipboard?.writeText(createdToken.token)" in copy_helper, "copy helper should read the fresh token only for clipboard copy", failures)
    require('setCreatedToken(current => current ? { ...current, token: "" } : current)' in copy_helper, "copy helper should clear the raw token after a successful copy", failures)
    require("window.setTimeout(() => setIssuedCredentialCopied(false)" not in copy_helper, "copy success must not re-enable raw token display after a timeout", failures)
    require("createdToken.token && !issuedCredentialCopied" in one_time_card, "one-time card should render the raw token only before copy", failures)
    require("{createdToken.token}</div>" in one_time_card, "one-time card should display the fresh token before copy", failures)
    require("disabled={!createdToken.token}" in one_time_card, "copy control should disable after the raw token is cleared", failures)
    require('data-testid="issued-credential-secret"' in one_time_card, "one-time secret display should be explicitly marked", failures)
    require("clearIssuedCredential" in one_time_card, "one-time card should include clear secret control", failures)
    require("credentialCannotBeReadAgain" in one_time_card, "one-time card should explain the no-reread contract", failures)
    require("createdToken.token" not in recent_enrollments, "recent enrollments list must not render raw token", failures)
    require("clearIssuedCredential();" in ai, "UI should have a clearIssuedCredential lifecycle call", failures)
    require("refresh = useCallback(async (options?: { preserveIssuedCredential?: boolean })" in ai, "refresh should support narrow preservation after issuance", failures)
    require("if (!options?.preserveIssuedCredential)" in ai, "ordinary refresh should clear issued credential", failures)
    require("await refresh({ preserveIssuedCredential: true });" in ai, "create/issue/rotate should preserve only the fresh one-time card", failures)
    require("onClick={() => void refresh()}" in ai, "manual refresh buttons should call refresh without preserving secrets", failures)

    forbidden_long_lived_reads = [
        match.group(0)
        for match in re.finditer(r"enrollments\.[A-Za-z0-9_?.()[\\]\\s=>{}`'\".,:-]*token", ai)
    ]
    require(not forbidden_long_lived_reads, f"raw token-like enrollment list read found: {forbidden_long_lived_reads[:3]}", failures)

    api_contract = api_contract_smoke(failures)
    output = {
        "ok": not failures,
        "operation": "enrollment_credential_ui_smoke",
        "files": [
            str(AI_EMPLOYEES.relative_to(ROOT)),
            str(LIVE_API.relative_to(ROOT)),
            str(SERVER.relative_to(ROOT)),
        ],
        "api_contract": api_contract,
        "contract": "issued credentials are shown only in the one-time issuance card; list/read APIs return token metadata plus token_omitted proof.",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
