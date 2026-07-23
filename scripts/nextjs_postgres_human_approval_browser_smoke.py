#!/usr/bin/env python3
"""Real-browser Human Approval acceptance for production Next.js/Postgres.

The smoke builds an isolated copy of the current Next.js source, starts that
artifact with ``next start``, and drives the approval UI through the Codex
Playwright CLI. Python is used only as the test orchestrator and as a fail-fast
observer for accidental legacy API traffic; no Python MIS API is started.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
PWCLI = Path.home() / ".codex" / "skills" / "playwright" / "scripts" / "playwright_cli.sh"
CONTRACT_ID = "nextjs_postgres_human_approval_browser_v1"
WORKSPACE_ID = "ws_browser_approval"
OTHER_WORKSPACE_ID = "ws_browser_approval_other"
APPROVER_USER_ID = "usr_browser_approval_approver"
VIEWER_USER_ID = "usr_browser_approval_viewer"
AGENT_ID = "agt_browser_approval"
APPROVE_ID = "ap_browser_approval_approve"
REJECT_ID = "ap_browser_approval_reject"
FOREIGN_ID = "ap_browser_approval_foreign"
APPROVER_USERNAME = "browser-approval-approver"
VIEWER_USERNAME = "browser-approval-viewer"
RAW_PROMPT_MARKER = "raw-browser-approval-prompt-private-marker"
RAW_RESPONSE_MARKER = "raw-browser-approval-response-private-marker"
TOKEN_MARKER = "browser-approval-private-token-marker"
EXPECTED_COMPILED_ROUTES = {
    "/api/mis/approvals/[approvalId]/[decision]/route",
    "/api/mis/approvals/route",
    "/api/mis/human-auth/login/route",
    "/api/mis/human-auth/session/route",
    "/workspace/approvals/page",
}

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import server  # noqa: E402
import storage_postgres_contract_smoke as pg_contract  # noqa: E402
from agentops_mis_storage.postgres import PostgresAdapter  # noqa: E402
from nextjs_production_python_proxy_fail_closed_smoke import (  # noqa: E402
    copy_isolated_next_app,
    run_next_build,
)
from storage_postgres_http_read_parity_smoke import connect_postgres_when_ready  # noqa: E402
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg  # noqa: E402


class PythonObserverHandler(BaseHTTPRequestHandler):
    hits = 0
    lock = threading.Lock()

    @classmethod
    def reset(cls) -> None:
        with cls.lock:
            cls.hits = 0

    @classmethod
    def hit_count(cls) -> int:
        with cls.lock:
            return cls.hits

    def respond(self) -> None:
        with type(self).lock:
            type(self).hits += 1
        length = min(int(self.headers.get("Content-Length") or 0), 64 * 1024)
        if length:
            self.rfile.read(length)
        body = json.dumps({"ok": False, "error": "unexpected_python_api_hit"}).encode("utf-8")
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self.respond()

    def do_POST(self) -> None:  # noqa: N802
        self.respond()

    def do_PUT(self) -> None:  # noqa: N802
        self.respond()

    def do_DELETE(self) -> None:  # noqa: N802
        self.respond()

    def log_message(self, _format: str, *_args: object) -> None:
        return


def reexec_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_APPROVAL_BROWSER_PG_REEXEC") == "1":
        return
    try:
        import hashlib
        import psycopg  # noqa: F401
        import xml.parsers.expat  # noqa: F401
        if not hasattr(hashlib, "scrypt"):
            raise ImportError("hashlib.scrypt unavailable")
        return
    except (ImportError, OSError):
        pass

    candidates: list[Path] = []
    if os.environ.get("AGENTOPS_APPROVAL_BROWSER_PYTHON"):
        candidates.append(Path(os.environ["AGENTOPS_APPROVAL_BROWSER_PYTHON"]))
    candidates.extend([
        BUNDLED_PYTHON,
        Path("/opt/homebrew/bin/python3.12"),
        Path("/opt/homebrew/bin/python3.11"),
        Path("/usr/bin/python3"),
    ])
    current = Path(sys.executable).resolve()
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            if candidate.resolve() == current:
                continue
        except OSError:
            continue
        probe = subprocess.run(
            [
                str(candidate),
                "-c",
                "import ast,hashlib,xml.parsers.expat; assert hasattr(hashlib,'scrypt')",
            ],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        pip = subprocess.run(
            [str(candidate), "-m", "pip", "--version"],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        if probe.returncode == 0 and pip.returncode == 0:
            os.environ["AGENTOPS_APPROVAL_BROWSER_PG_REEXEC"] = "1"
            os.execv(str(candidate), [str(candidate), str(Path(__file__).resolve()), *sys.argv[1:]])


def redact(value: object, sensitive: list[str]) -> str:
    output = str(value)
    secrets_to_redact = {
        item
        for item in sensitive
        if isinstance(item, str) and len(item.strip()) >= 8
    }
    for item in sorted(secrets_to_redact, key=len, reverse=True):
        output = output.replace(item, "[REDACTED]")
    output = re.sub(r"postgres(?:ql)?://[^\s'\"]+", "postgresql://[REDACTED]", output)
    return output


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def dsn_with_search_path(dsn: str, schema: str) -> str:
    parsed = urllib.parse.urlsplit(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("--postgres-dsn must be a postgres URL")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    options = [value for key, value in query if key == "options"]
    query = [(key, value) for key, value in query if key != "options"]
    query.append(("options", " ".join([*options, f"-c search_path={schema}"]).strip()))
    return urllib.parse.urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        urllib.parse.urlencode(query, quote_via=urllib.parse.quote),
        parsed.fragment,
    ))


def stop_process(proc: subprocess.Popen[str] | None, timeout: int = 10) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=5)


def run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def json_last_line(output: str) -> dict[str, Any]:
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return {}
    value = json.loads(lines[-1])
    return value if isinstance(value, dict) else {}


def run_migration(npm: str, dsn: str, *, check_only: bool = False) -> dict[str, Any]:
    env = os.environ.copy()
    env.update({
        "AGENTOPS_POSTGRES_DSN": dsn,
        "DATABASE_URL": dsn,
        "AGENTOPS_POSTGRES_SSL": "0",
        "NEXT_TELEMETRY_DISABLED": "1",
    })
    script = "schema:readiness" if check_only else "migrate:postgres"
    result = run_command([npm, "run", "--silent", script], cwd=NEXT_APP, env=env, timeout=90)
    if result.returncode != 0:
        raise RuntimeError(f"TypeScript schema command failed: {result.stderr[-1200:]}")
    return json_last_line(result.stdout)


def password_material(password: str) -> tuple[str, str, str]:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16_384, r=8, p=1, dklen=32)
    params = json.dumps({"keylen": 32, "n": 16_384, "name": "scrypt", "p": 1, "r": 8}, sort_keys=True)
    return derived.hex(), salt.hex(), params


def seed_user(
    adapter: PostgresAdapter,
    *,
    user_id: str,
    name: str,
    username: str,
    password: str,
    memberships: list[tuple[str, str]],
    now: str,
) -> None:
    adapter.execute(
        "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
        (user_id, name, f"{username}@example.invalid", "customer", now),
    )
    password_hash, password_salt, params = password_material(password)
    adapter.execute(
        """INSERT INTO human_login_credentials(
            credential_id,user_id,username,password_hash,password_salt,password_params_json,status,
            created_at,updated_at,last_login_at
        ) VALUES(?,?,?,?,?,?,'active',?,?,NULL)""",
        (f"hcred_{user_id}", user_id, username, password_hash, password_salt, params, now, now),
    )
    for workspace_id, role in memberships:
        adapter.execute(
            """INSERT INTO workspace_memberships(workspace_id,user_id,role,status,created_at,updated_at)
            VALUES(?,?,?,'active',?,?)""",
            (workspace_id, user_id, role, now, now),
        )


def seed_approval_graph(
    adapter: PostgresAdapter,
    *,
    approval_id: str,
    workspace_id: str,
    suffix: str,
    created_at: str,
) -> None:
    task_id = f"tsk_browser_approval_{suffix}"
    run_id = f"run_browser_approval_{suffix}"
    adapter.execute(
        """INSERT INTO tasks(
            task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,
            status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,'[]','waiting_approval','high',NULL,?,'medium',10,?,?)""",
        (
            task_id,
            workspace_id,
            f"Browser approval {suffix}",
            RAW_PROMPT_MARKER,
            APPROVER_USER_ID,
            AGENT_ID,
            RAW_RESPONSE_MARKER,
            created_at,
            created_at,
        ),
    )
    adapter.execute(
        """INSERT INTO runs(
            run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,
            input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,
            reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,
            approval_required,created_at
        ) VALUES(?,?,?,?,'openclaw','waiting_approval',?,NULL,NULL,?,?,NULL,NULL,0,0,0,0,NULL,NULL,NULL,NULL,NULL,1,?)""",
        (run_id, workspace_id, task_id, AGENT_ID, created_at, RAW_PROMPT_MARKER, RAW_RESPONSE_MARKER, created_at),
    )
    adapter.execute(
        """INSERT INTO approvals(
            approval_id,approval_kind,task_id,run_id,tool_call_id,requested_by_agent_id,approver_user_id,
            decision,reason,expires_at,created_at,decided_at
        ) VALUES(?,'run_execution',?,?,NULL,?,NULL,'pending',?,NULL,?,NULL)""",
        (approval_id, task_id, run_id, AGENT_ID, TOKEN_MARKER, created_at),
    )


def seed(adapter: PostgresAdapter, approver_password: str, viewer_password: str) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    now_text = now.isoformat()
    seed_user(
        adapter,
        user_id=APPROVER_USER_ID,
        name="Browser Approval Approver",
        username=APPROVER_USERNAME,
        password=approver_password,
        memberships=[(WORKSPACE_ID, "approver"), (OTHER_WORKSPACE_ID, "viewer")],
        now=now_text,
    )
    seed_user(
        adapter,
        user_id=VIEWER_USER_ID,
        name="Browser Approval Viewer",
        username=VIEWER_USERNAME,
        password=viewer_password,
        memberships=[(WORKSPACE_ID, "viewer")],
        now=now_text,
    )
    adapter.execute(
        """INSERT INTO agents(
            agent_id,name,role,description,runtime_type,model_provider,model_name,status,
            permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            AGENT_ID,
            "Browser Approval Agent",
            "operator",
            "Synthetic browser fixture",
            "openclaw",
            "fixture",
            "fixture",
            "idle",
            "restricted",
            "[]",
            0,
            APPROVER_USER_ID,
            now_text,
            now_text,
        ),
    )
    adapter.execute(
        """INSERT INTO runtime_connectors(
            runtime_connector_id,provider,connector_type,profile_name,base_url,binary_path,status,allow_real_run,
            require_confirm_run,trust_status,trust_note,trust_updated_at,last_health_at,last_error,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "rtc_agent_gateway_local",
            "agent_gateway",
            "local",
            "Human approval browser fixture",
            None,
            None,
            "ready",
            0,
            1,
            "trusted",
            None,
            now_text,
            now_text,
            None,
            now_text,
            now_text,
        ),
    )
    seed_approval_graph(
        adapter,
        approval_id=APPROVE_ID,
        workspace_id=WORKSPACE_ID,
        suffix="approve",
        created_at=now_text,
    )
    seed_approval_graph(
        adapter,
        approval_id=FOREIGN_ID,
        workspace_id=OTHER_WORKSPACE_ID,
        suffix="foreign",
        created_at=(now + dt.timedelta(seconds=1)).isoformat(),
    )
    adapter.commit()


def approval_evidence(adapter: PostgresAdapter, approval_id: str) -> dict[str, Any]:
    approval = adapter.fetchone(
        "SELECT decision,approver_user_id,task_id,run_id FROM approvals WHERE approval_id=?",
        (approval_id,),
    )
    request = adapter.fetchone(
        """SELECT user_id,idempotency_key_hash,request_hash,decision,status
        FROM human_approval_decision_requests WHERE approval_id=?""",
        (approval_id,),
    )
    request_count = int(adapter.fetchone(
        "SELECT COUNT(*) AS count FROM human_approval_decision_requests WHERE approval_id=?",
        (approval_id,),
    )["count"])
    audit_count = int(adapter.fetchone(
        """SELECT COUNT(*) AS count FROM audit_logs
        WHERE entity_type='approvals' AND entity_id=? AND action IN ('approval.approved','approval.rejected')""",
        (approval_id,),
    )["count"])
    audit = adapter.fetchone(
        """SELECT workspace_id,actor_type,actor_id,action,metadata_json FROM audit_logs
        WHERE entity_type='approvals' AND entity_id=? ORDER BY created_at DESC LIMIT 1""",
        (approval_id,),
    )
    event_count = 0
    if approval:
        event_count = int(adapter.fetchone(
            """SELECT COUNT(*) AS count FROM runtime_events
            WHERE run_id=? AND event_type IN ('approval.approved','approval.rejected')""",
            (approval["run_id"],),
        )["count"])
    adapter.commit()
    return {
        "approval": approval,
        "request": request,
        "request_count": request_count,
        "audit": audit,
        "audit_count": audit_count,
        "event_count": event_count,
    }


def wait_for_approval_decision(
    adapter: PostgresAdapter,
    approval_id: str,
    decision: str,
    *,
    timeout: int = 60,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    evidence: dict[str, Any] = {}
    while time.monotonic() < deadline:
        evidence = approval_evidence(adapter, approval_id)
        if (evidence.get("approval") or {}).get("decision") == decision:
            return evidence
        time.sleep(0.25)
    approval = evidence.get("approval") or {}
    raise RuntimeError(
        "Approval database decision did not converge; "
        f"decision={approval.get('decision')!r},request_count={evidence.get('request_count', 0)},"
        f"audit_count={evidence.get('audit_count', 0)},event_count={evidence.get('event_count', 0)}",
    )


def http_json(url: str) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8", errors="replace")
            value = json.loads(raw or "{}")
            return int(response.status), value if isinstance(value, dict) else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            value = json.loads(raw or "{}")
        except json.JSONDecodeError:
            value = {}
        return int(exc.code), value if isinstance(value, dict) else {}


def wait_for_next(base_url: str, proc: subprocess.Popen[str], log_path: Path, sensitive: list[str]) -> None:
    deadline = time.monotonic() + 90
    last = ""
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            tail = log_path.read_text(encoding="utf-8", errors="replace")[-3000:] if log_path.exists() else ""
            raise RuntimeError(redact(f"next start exited early: {tail}", sensitive))
        try:
            status, payload = http_json(f"{base_url}/api/mis/human-auth/session")
            if status == 401 and payload.get("error") == "human_auth_required":
                return
            last = f"{status}:{payload.get('error')}"
        except Exception as exc:  # pragma: no cover - diagnostics only
            last = str(exc)
        time.sleep(0.25)
    raise RuntimeError(redact(f"next start did not become ready: {last}", sensitive))


def playwright(env: dict[str, str], cwd: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return run_command(["bash", str(PWCLI), *args], cwd=cwd, env=env, timeout=timeout)


def require_playwright(
    env: dict[str, str],
    cwd: Path,
    *args: str,
    sensitive: list[str],
    timeout: int = 120,
) -> str:
    result = playwright(env, cwd, *args, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(redact(f"Playwright {' '.join(args[:1])} failed: {result.stderr[-1200:]}", sensitive))
    return result.stdout + result.stderr


def snapshot(env: dict[str, str], cwd: Path, sensitive: list[str]) -> str:
    return require_playwright(env, cwd, "snapshot", sensitive=sensitive)


def wait_snapshot(
    env: dict[str, str],
    cwd: Path,
    sensitive: list[str],
    predicate,
    label: str,
    *,
    timeout: int = 45,
) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = snapshot(env, cwd, sensitive)
        if predicate(last):
            return last
        time.sleep(0.35)
    diagnostics = {
        "sign_in": has_button(last, "Sign in"),
        "approve": has_button(last, "Approve"),
        "reject": has_button(last, "Reject"),
        "csrf_error": "CSRF" in last,
        "approval_id": APPROVE_ID in last,
        "approved": "approved" in last,
    }
    try:
        diagnostics["approval_retry"] = retry_status(env, cwd, sensitive)
    except Exception:
        diagnostics["approval_retry"] = "unavailable"
    raise RuntimeError(f"Browser did not render {label}; diagnostics={json.dumps(diagnostics, sort_keys=True)}")


def snapshot_ref(snapshot_text: str, label: str, control: str) -> str:
    for line in snapshot_text.splitlines():
        if label in line and control.lower() in line.lower():
            match = re.search(r"\[ref=([^\]]+)\]", line)
            if match:
                return match.group(1)
    raise RuntimeError(f"Browser ref unavailable for {control} {label}")


def has_button(snapshot_text: str, label: str) -> bool:
    return any(label in line and "button" in line.lower() for line in snapshot_text.splitlines())


def browser_login(
    env: dict[str, str],
    cwd: Path,
    sensitive: list[str],
    username: str,
    password: str,
    ready_predicate,
    ready_label: str,
) -> str:
    current = wait_snapshot(env, cwd, sensitive, lambda text: has_button(text, "Sign in"), "sign-in form")
    require_playwright(
        env,
        cwd,
        "fill",
        snapshot_ref(current, "Username", "textbox"),
        username,
        sensitive=sensitive,
    )
    descriptor, raw_password_script = tempfile.mkstemp(
        prefix="approval-browser-password-",
        suffix=".js",
        dir=cwd,
    )
    password_script = Path(raw_password_script)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(
                "async page => { await page.getByRole('textbox', {name: 'Password'}).fill("
                f"{json.dumps(password)}); }}",
            )
        require_playwright(
            env,
            cwd,
            "run-code",
            f"--filename={password_script}",
            sensitive=sensitive,
        )
    finally:
        password_script.unlink(missing_ok=True)
    current = snapshot(env, cwd, sensitive)
    require_playwright(
        env,
        cwd,
        "click",
        snapshot_ref(current, "Sign in", "button"),
        sensitive=sensitive,
    )
    return wait_snapshot(env, cwd, sensitive, ready_predicate, ready_label, timeout=60)


def browser_logout(env: dict[str, str], cwd: Path, sensitive: list[str], current: str) -> str:
    require_playwright(
        env,
        cwd,
        "click",
        snapshot_ref(current, "Sign out", "button"),
        sensitive=sensitive,
    )
    return wait_snapshot(env, cwd, sensitive, lambda text: has_button(text, "Sign in"), "signed-out state")


def arm_invalid_csrf(env: dict[str, str], cwd: Path, sensitive: list[str]) -> None:
    target = json.dumps(f"/api/mis/approvals/{APPROVE_ID}/approve")
    expression = f"""(() => {{
      const target = {target};
      const original = window.fetch.bind(window);
      window.fetch = async (input, init = {{}}) => {{
        const url = typeof input === 'string' ? input : String(input?.url || input);
        if (url.includes(target)) {{
          window.fetch = original;
          const headers = new Headers(init.headers || {{}});
          headers.set('X-AgentOps-CSRF', 'browser-invalid-csrf');
          return original(input, {{...init, headers}});
        }}
        return original(input, init);
      }};
      return 'AGENTOPS_INVALID_CSRF_ARMED';
    }})()"""
    output = require_playwright(env, cwd, "eval", expression, sensitive=sensitive)
    if "AGENTOPS_INVALID_CSRF_ARMED" not in output:
        raise RuntimeError("Browser CSRF interception did not arm")


def arm_duplicate_retry(env: dict[str, str], cwd: Path, sensitive: list[str]) -> None:
    target = json.dumps(f"/api/mis/approvals/{APPROVE_ID}/approve")
    expression = f"""(() => {{
      const target = {target};
      const original = window.fetch.bind(window);
      window.__agentopsApprovalRetry = 'armed';
      window.__agentopsApprovalRetryErrors = 'missing:missing';
      window.fetch = async (input, init = {{}}) => {{
        const url = typeof input === 'string' ? input : String(input?.url || input);
        if (url.includes(target)) {{
          window.fetch = original;
          if (typeof input !== 'string' || typeof init.body !== 'string') {{
            window.__agentopsApprovalRetry = 'request_shape_error';
            return original(input, init);
          }}
          const replayInit = () => ({{
            ...init,
            headers: new Headers(init.headers || {{}}),
          }});
          let primary;
          try {{
            primary = await original(input, replayInit());
            const primaryPayload = await primary.clone().json().catch(() => ({{}}));
            const primaryError = typeof primaryPayload?.error === 'string'
              && /^[a-z0-9_]{{1,80}}$/.test(primaryPayload.error)
              ? primaryPayload.error
              : 'none';
            window.__agentopsApprovalRetryErrors = `${{primaryError}}:missing`;
            window.__agentopsApprovalRetry = `primary:${{primary.status}}`;
          }} catch (_error) {{
            window.__agentopsApprovalRetry = 'primary_error';
            throw _error;
          }}
          try {{
            const retry = await original(input, replayInit());
            const retryPayload = await retry.clone().json().catch(() => ({{}}));
            const retryError = typeof retryPayload?.error === 'string'
              && /^[a-z0-9_]{{1,80}}$/.test(retryPayload.error)
              ? retryPayload.error
              : 'none';
            const primaryError = String(window.__agentopsApprovalRetryErrors || 'none:missing').split(':')[0];
            window.__agentopsApprovalRetryErrors = `${{primaryError}}:${{retryError}}`;
            window.__agentopsApprovalRetry = `${{primary.status}}:${{retry.status}}`;
          }} catch (_error) {{
            window.__agentopsApprovalRetry = `${{primary.status}}:retry_error`;
          }}
          return primary;
        }}
        return original(input, init);
      }};
      return 'AGENTOPS_DUPLICATE_RETRY_ARMED';
    }})()"""
    output = require_playwright(env, cwd, "eval", expression, sensitive=sensitive)
    if "AGENTOPS_DUPLICATE_RETRY_ARMED" not in output:
        raise RuntimeError("Browser duplicate retry interception did not arm")


def retry_status(env: dict[str, str], cwd: Path, sensitive: list[str]) -> str:
    output = require_playwright(
        env,
        cwd,
        "eval",
        "(() => window.__agentopsApprovalRetry || 'missing')()",
        sensitive=sensitive,
    )
    match = re.search(
        r"\b(\d{3}:\d{3}|primary:\d{3}|\d{3}:retry_error|request_shape_error|primary_error|armed|missing)\b",
        output,
    )
    return match.group(1) if match else "missing"


def retry_response_errors(env: dict[str, str], cwd: Path, sensitive: list[str]) -> str:
    output = require_playwright(
        env,
        cwd,
        "eval",
        "(() => 'AGENTOPS_RETRY_ERRORS=' + (window.__agentopsApprovalRetryErrors || 'missing:missing'))()",
        sensitive=sensitive,
    )
    match = re.search(r"AGENTOPS_RETRY_ERRORS=([a-z0-9_]{1,80}:[a-z0-9_]{1,80})", output)
    return match.group(1) if match else "missing:missing"


def wait_for_retry_result(
    env: dict[str, str],
    cwd: Path,
    sensitive: list[str],
    *,
    timeout: int = 60,
) -> str:
    deadline = time.monotonic() + timeout
    status = "missing"
    while time.monotonic() < deadline:
        status = retry_status(env, cwd, sensitive)
        if re.fullmatch(r"\d{3}:\d{3}", status) or status.endswith("_error"):
            return status
        time.sleep(0.25)
    raise RuntimeError(f"Browser approval retry did not complete; retry_status={status}")


def assert_decision_evidence(
    evidence: dict[str, Any],
    *,
    decision: str,
    action: str,
) -> None:
    approval = evidence.get("approval") or {}
    request = evidence.get("request") or {}
    audit = evidence.get("audit") or {}
    metadata = str(audit.get("metadata_json") or "")
    if not (
        approval.get("decision") == decision
        and approval.get("approver_user_id") == APPROVER_USER_ID
        and evidence.get("request_count") == 1
        and request.get("user_id") == APPROVER_USER_ID
        and request.get("decision") == decision
        and request.get("status") == "completed"
        and re.fullmatch(r"[a-f0-9]{64}", str(request.get("idempotency_key_hash") or "")) is not None
        and re.fullmatch(r"[a-f0-9]{64}", str(request.get("request_hash") or "")) is not None
        and evidence.get("audit_count") == 1
        and audit.get("workspace_id") == WORKSPACE_ID
        and audit.get("actor_type") == "user"
        and audit.get("actor_id") == APPROVER_USER_ID
        and audit.get("action") == action
        and "credentials_omitted" in metadata
        and "raw_body_omitted" in metadata
        and evidence.get("event_count") == 1
    ):
        raise AssertionError(f"Approval evidence mismatch for {decision}")


def compiled_routes(app_dir: Path) -> set[str]:
    manifest_path = app_dir / ".next" / "server" / "app-paths-manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Next production build omitted app-paths-manifest.json")
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    routes = {str(item) for item in value} if isinstance(value, dict) else set()
    missing = EXPECTED_COMPILED_ROUTES - routes
    if missing:
        raise RuntimeError(f"Next production build omitted required approval routes: {sorted(missing)}")
    build_id = app_dir / ".next" / "BUILD_ID"
    if not build_id.is_file() or not build_id.read_text(encoding="utf-8").strip():
        raise RuntimeError("Next production build omitted BUILD_ID")
    return routes


def start_observer() -> tuple[ThreadingHTTPServer, threading.Thread]:
    PythonObserverHandler.reset()
    server_instance = ThreadingHTTPServer(("127.0.0.1", 0), PythonObserverHandler)
    thread = threading.Thread(target=server_instance.serve_forever, daemon=True)
    thread.start()
    return server_instance, thread


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the production Next.js/Postgres real-browser Human Approval smoke.",
    )
    parser.add_argument(
        "--postgres-dsn",
        required=True,
        help="Postgres URL; the smoke creates and drops a unique isolated schema.",
    )
    parser.add_argument("--no-install-driver", action="store_true")
    args = parser.parse_args()

    reexec_with_bundled_python_if_needed()
    node = shutil.which("node")
    npm = shutil.which("npm")
    npx = shutil.which("npx")
    if not node or not npm or not npx:
        print(json.dumps({
            "ok": False,
            "contract": CONTRACT_ID,
            "error": "node_npm_npx_required",
            "python_api_started": False,
        }, indent=2, sort_keys=True))
        return 1
    if not PWCLI.is_file() or not (NEXT_APP / "node_modules" / "next").exists():
        print(json.dumps({
            "ok": False,
            "contract": CONTRACT_ID,
            "error": "next_or_playwright_dependency_missing",
            "python_api_started": False,
        }, indent=2, sort_keys=True))
        return 1

    schema = f"agentops_approval_browser_{secrets.token_hex(8)}"
    approver_password = f"Approve-{secrets.token_urlsafe(18)}"
    viewer_password = f"Viewer-{secrets.token_urlsafe(18)}"
    hmac_key = secrets.token_urlsafe(48)
    sensitive = [
        args.postgres_dsn,
        approver_password,
        viewer_password,
        hmac_key,
        RAW_PROMPT_MARKER,
        RAW_RESPONSE_MARKER,
        TOKEN_MARKER,
    ]
    checks: dict[str, bool] = {}
    error = ""
    runtime_error_diagnostics = ""
    cleanup_errors: list[str] = []
    runtime_dsn = ""
    schema_created = False
    temp = tempfile.TemporaryDirectory(prefix="agentops-approval-browser-")
    temp_root = Path(temp.name)
    app_dir = temp_root / "next-app"
    build_log = temp_root / "next-build.log"
    next_log = temp_root / "next-start.log"
    next_log_handle = None
    next_proc: subprocess.Popen[str] | None = None
    observer: ThreadingHTTPServer | None = None
    observer_thread: threading.Thread | None = None
    adapter: PostgresAdapter | None = None
    setup_adapter: PostgresAdapter | None = None
    pw_env: dict[str, str] | None = None
    browser_snapshots: list[str] = []

    try:
        driver_ok, driver_status = ensure_psycopg(temp_root / "driver", install=not args.no_install_driver)
        if not driver_ok:
            raise RuntimeError(f"Optional psycopg driver unavailable: {driver_status}")

        setup_adapter = connect_postgres_when_ready(args.postgres_dsn, secret="")
        setup_adapter.execute(f'CREATE SCHEMA "{schema}"')
        setup_adapter.commit()
        setup_adapter.close()
        setup_adapter = None
        schema_created = True
        runtime_dsn = dsn_with_search_path(args.postgres_dsn, schema)
        sensitive.append(runtime_dsn)

        adapter = connect_postgres_when_ready(runtime_dsn, secret="")
        adapter.executescript(pg_contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
        adapter.commit()
        migrated = run_migration(npm, runtime_dsn)
        ready = run_migration(npm, runtime_dsn, check_only=True)
        schema_row = adapter.fetchone(
            """SELECT version,schema_contract FROM agentops_schema_migrations
            WHERE component='human_session_memory_review'""",
        )
        adapter.commit()
        checks["isolated_postgres_schema_v4_ready"] = bool(
            migrated.get("ready") is True
            and ready.get("ready") is True
            and schema_row
            and schema_row["version"] == "20260719_approval_kind_bindings_v4"
            and schema_row["schema_contract"] == "agentops-human-session-approval-kind-bindings-contract-v4"
        )
        if not checks["isolated_postgres_schema_v4_ready"]:
            raise AssertionError("Isolated Postgres approval schema is not v4-ready")

        seed(adapter, approver_password, viewer_password)
        checks["fixture_contains_approve_reject_and_foreign_workspace"] = True

        copy_isolated_next_app(app_dir)
        observer, observer_thread = start_observer()
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        next_env = {
            key: os.environ[key]
            for key in ("HOME", "LANG", "LC_ALL", "PATH", "SHELL", "TMPDIR", "TMP", "TEMP")
            if os.environ.get(key)
        }
        next_env.update({
            "AGENTOPS_DEPLOYMENT_MODE": "production",
            "AGENTOPS_CONTROL_PLANE_MODE": "postgres",
            "AGENTOPS_POSTGRES_DSN": runtime_dsn,
            "DATABASE_URL": runtime_dsn,
            "AGENTOPS_POSTGRES_SSL": "0",
            "AGENTOPS_API_BASE": f"http://127.0.0.1:{observer.server_port}/api",
            "AGENTOPS_ALLOWED_ORIGINS": base_url,
            "AGENTOPS_HUMAN_SESSION_HMAC_KEY": hmac_key,
            "AGENTOPS_HUMAN_LOGIN_CONCURRENCY": "1",
            "NEXT_TELEMETRY_DISABLED": "1",
            "NODE_ENV": "production",
        })
        next_cli = app_dir / "node_modules" / "next" / "dist" / "bin" / "next"
        run_next_build(node, next_cli, app_dir, next_env, build_log)
        routes = compiled_routes(app_dir)
        checks["isolated_next_build_has_required_routes"] = EXPECTED_COMPILED_ROUTES.issubset(routes)

        next_log_handle = next_log.open("w", encoding="utf-8")
        next_proc = subprocess.Popen(
            [node, str(next_cli), "start", "-p", str(port)],
            cwd=app_dir,
            env=next_env,
            text=True,
            stdout=next_log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        wait_for_next(base_url, next_proc, next_log, sensitive)
        checks["production_next_start_ready"] = True

        pw_env = os.environ.copy()
        pw_env["PLAYWRIGHT_CLI_SESSION"] = f"approval-browser-{secrets.token_hex(6)}"
        opened = require_playwright(
            pw_env,
            temp_root,
            "open",
            f"{base_url}/workspace/approvals",
            sensitive=sensitive,
            timeout=180,
        )
        browser_snapshots.append(opened)
        initial = wait_snapshot(
            pw_env,
            temp_root,
            sensitive,
            lambda text: has_button(text, "Sign in"),
            "unauthenticated approval sign-in",
            timeout=60,
        )
        browser_snapshots.append(initial)
        checks["unauthenticated_browser_shows_login"] = has_button(initial, "Sign in")

        viewer = browser_login(
            pw_env,
            temp_root,
            sensitive,
            VIEWER_USERNAME,
            viewer_password,
            lambda text: FOREIGN_ID not in text and APPROVE_ID in text,
            "viewer approval list",
        )
        browser_snapshots.append(viewer)
        checks["viewer_has_no_approval_buttons"] = (
            APPROVE_ID in viewer
            and not has_button(viewer, "Approve")
            and not has_button(viewer, "Reject")
        )
        viewer_signed_out = browser_logout(pw_env, temp_root, sensitive, viewer)
        browser_snapshots.append(viewer_signed_out)

        approver = browser_login(
            pw_env,
            temp_root,
            sensitive,
            APPROVER_USERNAME,
            approver_password,
            lambda text: "Select workspace" in text and "combobox" in text.lower(),
            "approver explicit workspace selection",
        )
        browser_snapshots.append(approver)
        workspace_ref = snapshot_ref(approver, "Workspace", "combobox")
        require_playwright(
            pw_env,
            temp_root,
            "select",
            workspace_ref,
            OTHER_WORKSPACE_ID,
            sensitive=sensitive,
        )
        foreign = wait_snapshot(
            pw_env,
            temp_root,
            sensitive,
            lambda text: FOREIGN_ID in text,
            "foreign workspace approval",
        )
        browser_snapshots.append(foreign)
        checks["foreign_workspace_is_explicit_and_read_only"] = (
            FOREIGN_ID in foreign
            and APPROVE_ID not in foreign
            and not has_button(foreign, "Approve")
            and not has_button(foreign, "Reject")
        )
        workspace_ref = snapshot_ref(foreign, "Workspace", "combobox")
        require_playwright(
            pw_env,
            temp_root,
            "select",
            workspace_ref,
            WORKSPACE_ID,
            sensitive=sensitive,
        )
        approver_workspace = wait_snapshot(
            pw_env,
            temp_root,
            sensitive,
            lambda text: APPROVE_ID in text and has_button(text, "Approve") and has_button(text, "Reject"),
            "approver workspace approval controls",
        )
        browser_snapshots.append(approver_workspace)
        checks["approver_selected_workspace_and_cross_workspace_hidden"] = (
            APPROVE_ID in approver_workspace and FOREIGN_ID not in approver_workspace
        )
        checks["approve_and_reject_ui_visible_to_approver"] = (
            has_button(approver_workspace, "Approve") and has_button(approver_workspace, "Reject")
        )

        arm_invalid_csrf(pw_env, temp_root, sensitive)
        require_playwright(
            pw_env,
            temp_root,
            "click",
            snapshot_ref(approver_workspace, "Approve", "button"),
            sensitive=sensitive,
        )
        csrf_rejected = wait_snapshot(
            pw_env,
            temp_root,
            sensitive,
            lambda text: "CSRF" in text and APPROVE_ID in text and has_button(text, "Approve"),
            "CSRF rejection in approval UI",
        )
        browser_snapshots.append(csrf_rejected)
        csrf_evidence = approval_evidence(adapter, APPROVE_ID)
        checks["csrf_failure_is_visible_and_non_mutating"] = bool(
            csrf_evidence["approval"]
            and csrf_evidence["approval"]["decision"] == "pending"
            and csrf_evidence["request_count"] == 0
            and csrf_evidence["audit_count"] == 0
            and csrf_evidence["event_count"] == 0
        )
        if not checks["csrf_failure_is_visible_and_non_mutating"]:
            raise AssertionError("Invalid browser CSRF mutated approval evidence")

        arm_duplicate_retry(pw_env, temp_root, sensitive)
        require_playwright(
            pw_env,
            temp_root,
            "click",
            snapshot_ref(csrf_rejected, "Approve", "button"),
            sensitive=sensitive,
        )
        retry_result = wait_for_retry_result(pw_env, temp_root, sensitive)
        if retry_result != "200:200":
            raise RuntimeError(
                "Browser duplicate approval retry failed; "
                f"retry_status={retry_result},response_errors={retry_response_errors(pw_env, temp_root, sensitive)}",
            )
        approved_evidence = wait_for_approval_decision(adapter, APPROVE_ID, "approved")
        approved = wait_snapshot(
            pw_env,
            temp_root,
            sensitive,
            lambda text: APPROVE_ID in text and "approved" in text,
            "approved decision history",
            timeout=60,
        )
        browser_snapshots.append(approved)
        assert_decision_evidence(
            approved_evidence,
            decision="approved",
            action="approval.approved",
        )
        checks["single_ui_click_duplicate_retry_is_idempotent"] = retry_result == "200:200"
        if not checks["single_ui_click_duplicate_retry_is_idempotent"]:
            raise AssertionError("Browser duplicate approval retry did not return two successful idempotent responses")
        checks["approved_db_audit_records_real_user_id"] = True

        approved_counts = (
            approved_evidence["request_count"],
            approved_evidence["audit_count"],
            approved_evidence["event_count"],
        )
        for _ in range(2):
            require_playwright(pw_env, temp_root, "reload", sensitive=sensitive)
            approved = wait_snapshot(
                pw_env,
                temp_root,
                sensitive,
                lambda text: APPROVE_ID in text and "approved" in text,
                "approved decision after reload",
            )
            browser_snapshots.append(approved)
        reloaded_evidence = approval_evidence(adapter, APPROVE_ID)
        checks["browser_refresh_does_not_duplicate_evidence"] = approved_counts == (
            reloaded_evidence["request_count"],
            reloaded_evidence["audit_count"],
            reloaded_evidence["event_count"],
        )
        if not checks["browser_refresh_does_not_duplicate_evidence"]:
            raise AssertionError("Browser reload duplicated approval evidence")

        seed_approval_graph(
            adapter,
            approval_id=REJECT_ID,
            workspace_id=WORKSPACE_ID,
            suffix="reject",
            created_at=(dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=2)).isoformat(),
        )
        adapter.commit()
        current = snapshot(pw_env, temp_root, sensitive)
        require_playwright(
            pw_env,
            temp_root,
            "click",
            snapshot_ref(current, "Refresh Approvals", "button"),
            sensitive=sensitive,
        )
        reject_ready = wait_snapshot(
            pw_env,
            temp_root,
            sensitive,
            lambda text: REJECT_ID in text and has_button(text, "Reject"),
            "reject approval control",
        )
        browser_snapshots.append(reject_ready)
        require_playwright(
            pw_env,
            temp_root,
            "click",
            snapshot_ref(reject_ready, "Reject", "button"),
            sensitive=sensitive,
        )
        rejected = wait_snapshot(
            pw_env,
            temp_root,
            sensitive,
            lambda text: REJECT_ID in text and "rejected" in text,
            "rejected decision history",
            timeout=60,
        )
        browser_snapshots.append(rejected)
        rejected_evidence = approval_evidence(adapter, REJECT_ID)
        assert_decision_evidence(
            rejected_evidence,
            decision="rejected",
            action="approval.rejected",
        )
        checks["reject_ui_closes_db_audit_with_real_user_id"] = True

        foreign_evidence = approval_evidence(adapter, FOREIGN_ID)
        checks["foreign_workspace_approval_remains_unmodified"] = bool(
            foreign_evidence["approval"]
            and foreign_evidence["approval"]["decision"] == "pending"
            and foreign_evidence["request_count"] == 0
            and foreign_evidence["audit_count"] == 0
        )
        rendered = "\n".join(browser_snapshots)
        checks["sensitive_token_raw_prompt_response_not_rendered"] = all(
            value not in rendered
            for value in [
                approver_password,
                viewer_password,
                hmac_key,
                RAW_PROMPT_MARKER,
                RAW_RESPONSE_MARKER,
                TOKEN_MARKER,
            ]
        )
        runtime_logs = ""
        if next_log.exists():
            runtime_logs += next_log.read_text(encoding="utf-8", errors="replace")
        if build_log.exists():
            runtime_logs += build_log.read_text(encoding="utf-8", errors="replace")
        checks["sensitive_values_not_emitted_by_next_build_or_start"] = all(
            value not in runtime_logs
            for value in [
                approver_password,
                viewer_password,
                hmac_key,
                RAW_PROMPT_MARKER,
                RAW_RESPONSE_MARKER,
                TOKEN_MARKER,
            ]
        )
        checks["python_observer_zero_hits_during_browser_flow"] = PythonObserverHandler.hit_count() == 0
        if not all(checks.values()):
            raise AssertionError("One or more Human Approval browser checks failed")
    except Exception as exc:  # pragma: no cover - exercised on environment/product failures
        error = redact(f"{type(exc).__name__}: {exc}", sensitive)
        if next_log.exists():
            diagnostic_lines = [
                line
                for line in next_log.read_text(encoding="utf-8", errors="replace").splitlines()
                if "agentops.approval_decision_unavailable" in line
            ]
            if diagnostic_lines:
                runtime_error_diagnostics = redact(diagnostic_lines[-1][-1200:], sensitive)
        if os.environ.get("AGENTOPS_SMOKE_TRACEBACK") == "1":
            error = redact(f"{error}\n{traceback.format_exc()}", sensitive)
    finally:
        if pw_env is not None:
            try:
                close_result = playwright(pw_env, temp_root, "close", timeout=30)
                if close_result.returncode != 0:
                    cleanup_errors.append("browser_close_failed")
            except Exception as exc:  # pragma: no cover - cleanup diagnostics
                cleanup_errors.append(redact(f"browser_close:{exc}", sensitive))
        stop_process(next_proc)
        if next_log_handle is not None:
            next_log_handle.close()
        if observer is not None:
            observer.shutdown()
            observer.server_close()
        if observer_thread is not None:
            observer_thread.join(timeout=5)
            if observer_thread.is_alive():
                cleanup_errors.append("observer_thread_alive")
        if adapter is not None:
            try:
                adapter.close()
            except Exception as exc:  # pragma: no cover - cleanup diagnostics
                cleanup_errors.append(redact(f"adapter_close:{exc}", sensitive))
        if setup_adapter is not None:
            try:
                setup_adapter.close()
            except Exception as exc:  # pragma: no cover - cleanup diagnostics
                cleanup_errors.append(redact(f"setup_adapter_close:{exc}", sensitive))
        if schema_created:
            cleanup_adapter: PostgresAdapter | None = None
            try:
                cleanup_adapter = connect_postgres_when_ready(args.postgres_dsn, secret="")
                cleanup_adapter.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                cleanup_adapter.commit()
            except Exception as exc:  # pragma: no cover - cleanup diagnostics
                cleanup_errors.append(redact(f"schema_drop:{exc}", sensitive))
            finally:
                if cleanup_adapter is not None:
                    cleanup_adapter.close()
        temp_path = Path(temp.name)
        try:
            temp.cleanup()
        except Exception as exc:  # pragma: no cover - cleanup diagnostics
            cleanup_errors.append(redact(f"temp_cleanup:{exc}", sensitive))
        checks["all_temporary_processes_and_artifacts_cleaned"] = bool(
            (next_proc is None or next_proc.poll() is not None)
            and (observer_thread is None or not observer_thread.is_alive())
            and not temp_path.exists()
            and not cleanup_errors
        )
        checks["python_observer_zero_hits"] = PythonObserverHandler.hit_count() == 0

    failed_checks = sorted(name for name, passed in checks.items() if not passed)
    ok = not error and not cleanup_errors and not failed_checks and bool(checks)
    payload: dict[str, Any] = {
        "ok": ok,
        "contract": CONTRACT_ID,
        "control_plane": "nextjs_typescript_postgres",
        "browser": "playwright_real_browser",
        "production_runtime": "isolated_next_build_then_next_start",
        "python_api_started": False,
        "fake_python_observer_hits": PythonObserverHandler.hit_count(),
        "checks": checks,
        "failed_checks": failed_checks,
        "cleanup_complete": checks.get("all_temporary_processes_and_artifacts_cleaned", False),
        "sensitive_output_omitted": True,
    }
    if error:
        payload["error"] = error
    if runtime_error_diagnostics:
        payload["runtime_error_diagnostics"] = runtime_error_diagnostics
    if cleanup_errors:
        payload["cleanup_errors"] = cleanup_errors
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    if any(item and item in serialized for item in sensitive):
        payload = {
            "ok": False,
            "contract": CONTRACT_ID,
            "error": "sensitive_output_guard_failed",
            "python_api_started": False,
            "fake_python_observer_hits": PythonObserverHandler.hit_count(),
            "cleanup_complete": checks.get("all_temporary_processes_and_artifacts_cleaned", False),
            "sensitive_output_omitted": True,
        }
        serialized = json.dumps(payload, indent=2, sort_keys=True)
    print(serialized)
    return 0 if payload.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
