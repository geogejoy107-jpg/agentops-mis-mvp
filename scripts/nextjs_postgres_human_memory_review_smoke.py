#!/usr/bin/env python3
"""Exercise Human Session candidate Memory Review on the Next.js/Postgres control plane."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
MIGRATION = ROOT / "migrations" / "postgres" / "20260718_human_session_memory_review.sql"
CONTRACT_ID = "nextjs_postgres_human_memory_review_v1"
CURRENT_SCHEMA_VERSION = "20260724_customer_delivery_run_unique_v5"
CURRENT_SCHEMA_CONTRACT = "agentops-human-session-customer-delivery-run-unique-contract-v5"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
from agentops_mis_storage.postgres import PostgresAdapter  # noqa: E402
from nextjs_playwright_snapshot_smoke import free_port, start_process, stop_process  # noqa: E402
from storage_postgres_http_read_parity_smoke import connect_postgres_when_ready  # noqa: E402
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg, mapped_port  # noqa: E402


WORKSPACE_ID = "ws_human_review_smoke"
OTHER_WORKSPACE_ID = "ws_human_review_other"
APPROVER_A = "usr_human_approver_a"
APPROVER_B = "usr_human_approver_b"
OPERATOR = "usr_human_operator"
SESSION_RACE_USER = "usr_human_session_race"
MEMBERSHIP_RACE_USER = "usr_human_membership_race"
DISABLED_USER = "usr_human_disabled"
USERS = {
    APPROVER_A: ("approver-a", "approver"),
    APPROVER_B: ("approver-b", "approver"),
    OPERATOR: ("operator", "operator"),
    SESSION_RACE_USER: ("session-race", "approver"),
    MEMBERSHIP_RACE_USER: ("membership-race", "approver"),
    DISABLED_USER: ("disabled-user", "approver"),
}
MEM_APPROVE = "mem_human_approve"
MEM_REJECT = "mem_human_reject"
MEM_SAME_KEY = "mem_human_same_key"
MEM_SINGLE_WINNER = "mem_human_single_winner"
MEM_SESSION_RACE = "mem_human_session_race"
MEM_MEMBERSHIP_RACE = "mem_human_membership_race"
MEM_OPERATOR = "mem_human_operator_denied"
MEM_FOREIGN = "mem_human_foreign"
MEM_MISSING = "mem_human_missing"
PWCLI = Path.home() / ".codex" / "skills" / "playwright" / "scripts" / "playwright_cli.sh"


def reexec_self_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_HUMAN_REVIEW_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists() or Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_HUMAN_REVIEW_PG_REEXEC"] = "1"
        os.execv(str(BUNDLED_PYTHON), [str(BUNDLED_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


def redact(value: object, sensitive: list[str]) -> str:
    output = str(value)
    for item in sorted((item for item in sensitive if item), key=len, reverse=True):
        output = output.replace(item, "[REDACTED]")
    return output


def unavailable(message: str, *, skip: bool, sensitive: list[str] | None = None) -> int:
    print(json.dumps({
        "ok": bool(skip),
        "skipped": bool(skip),
        "contract": CONTRACT_ID,
        "reason": redact(message, sensitive or []),
        "dynamic_postgres_smoke": True,
        "python_api_started": False,
        "real_external_side_effects": False,
    }, indent=2, sort_keys=True))
    return 0 if skip else 1


def check(checks: dict[str, bool], failures: list[str], name: str, condition: bool) -> None:
    checks[name] = bool(condition)
    if not condition:
        failures.append(name)


def dsn_with_search_path(dsn: str, schema: str) -> str:
    parsed = urllib.parse.urlsplit(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("--postgres-dsn must be a postgres URL")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    existing = [value for key, value in query if key == "options"]
    query = [(key, value) for key, value in query if key != "options"]
    query.append(("options", " ".join([*existing, f"-c search_path={schema}"]).strip()))
    return urllib.parse.urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        urllib.parse.urlencode(query, quote_via=urllib.parse.quote),
        parsed.fragment,
    ))


def http_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    *,
    raw_body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 20,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    def normalized_headers(message) -> dict[str, str]:
        output: dict[str, str] = {}
        for key in message.keys():
            values = message.get_all(key) or []
            output[key.lower()] = "\n".join(values)
        return output

    request_headers = dict(headers or {})
    data = raw_body
    if body is not None:
        data = json.dumps(body, sort_keys=True).encode("utf-8")
    if data is not None:
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            payload = json.loads(raw) if raw else {}
            return int(response.status), payload, normalized_headers(response.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw_omitted": True}
        return int(exc.code), payload, normalized_headers(exc.headers)


def http_status(url: str, headers: dict[str, str] | None = None, timeout: int = 60) -> int:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(4096)
            return int(response.status)
    except urllib.error.HTTPError as exc:
        exc.read(4096)
        return int(exc.code)


def wait_for_next(base_url: str, proc: subprocess.Popen[str], sensitive: list[str]) -> None:
    deadline = time.time() + 75
    last = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=2)
            raise RuntimeError(redact(f"Next.js exited early: {stdout} {stderr}", sensitive))
        try:
            status, payload, _headers = http_json("GET", f"{base_url}/api/mis/human-auth/session")
            if status == 401 and payload.get("error") == "human_auth_required":
                return
            last = f"{status}:{payload.get('error')}"
        except Exception as exc:  # pragma: no cover - diagnostic path
            last = str(exc)
        time.sleep(0.25)
    raise RuntimeError(redact(f"Next.js Human Session route was not ready: {last}", sensitive))


def wait_for_proxy_next(
    base_url: str,
    proc: subprocess.Popen[str],
    sensitive: list[str],
    *,
    production_fail_closed: bool = False,
) -> None:
    deadline = time.time() + 75
    last = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=2)
            raise RuntimeError(redact(f"Next.js proxy exited early: {stdout} {stderr}", sensitive))
        try:
            status, payload, _headers = http_json("GET", f"{base_url}/api/mis/dashboard/metrics")
            if status == 200 and payload.get("ok") is True:
                return
            if (
                production_fail_closed
                and status == 503
                and payload.get("error") == "typescript_control_plane_unavailable"
            ):
                return
            last = f"{status}:{payload.get('error')}"
        except Exception as exc:  # pragma: no cover - diagnostic path
            last = str(exc)
        time.sleep(0.25)
    raise RuntimeError(redact(f"Next.js proxy route was not ready: {last}", sensitive))


def node_chunked_probe(
    node_binary: str,
    url: str,
    first_chunk_bytes: int,
    headers: dict[str, str],
) -> dict[str, Any]:
    source = r"""
const http = require('node:http');
const target = new URL(process.argv[1]);
const firstChunkBytes = Number(process.argv[2]);
const suppliedHeaders = JSON.parse(process.argv[3]);
let finished = false;
const started = Date.now();
const request = http.request({
  protocol: target.protocol,
  hostname: target.hostname,
  port: target.port,
  path: target.pathname + target.search,
  method: 'POST',
  headers: { ...suppliedHeaders, 'Content-Type': 'application/json' },
}, (response) => {
  let raw = '';
  response.setEncoding('utf8');
  response.on('data', (chunk) => { raw += chunk; });
  response.on('end', () => {
    if (finished) return;
    finished = true;
    clearTimeout(failTimer);
    let payload = {};
    try { payload = raw ? JSON.parse(raw) : {}; } catch { payload = {}; }
    process.stdout.write(JSON.stringify({
      status: response.statusCode,
      error: payload.error || '',
      elapsed_ms: Date.now() - started,
      content_length_sent: false,
    }));
  });
});
request.on('error', (error) => {
  if (finished) return;
  finished = true;
  clearTimeout(failTimer);
  process.stderr.write(error.message);
  process.exitCode = 1;
});
request.write('x'.repeat(Math.floor(firstChunkBytes / 2)));
request.end('x'.repeat(Math.ceil(firstChunkBytes / 2)));
const failTimer = setTimeout(() => {
  if (finished) return;
  finished = true;
  request.destroy();
  process.stderr.write('chunked probe timed out');
  process.exitCode = 1;
}, 10000);
"""
    result = subprocess.run(
        [node_binary, "-e", source, url, str(first_chunk_bytes), json.dumps(headers, sort_keys=True)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Node chunked probe failed: {result.stderr[-300:]}")
    return json.loads(result.stdout)


def playwright(env: dict[str, str], *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(PWCLI), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def playwright_snapshot(env: dict[str, str]) -> str:
    result = playwright(env, "snapshot")
    if result.returncode != 0:
        raise RuntimeError(f"Playwright snapshot failed: {result.stderr[-300:]}")
    return result.stdout + result.stderr


def safe_snapshot_diagnostics(snapshot: str) -> dict[str, bool]:
    lowered = snapshot.lower()
    return {
        "contains_sign_in": "sign in" in lowered,
        "contains_next_error": any(marker in lowered for marker in (
            "application error",
            "internal server error",
            "next.js error",
            "__next_error__",
        )),
        "contains_loading": "loading" in lowered,
        "contains_auth_error": any(marker in lowered for marker in (
            "human_auth_",
            "human session is invalid",
            "unable to validate human session",
        )),
    }


def wait_for_snapshot(env: dict[str, str], predicate, label: str, timeout_sec: int = 30) -> str:
    deadline = time.time() + timeout_sec
    last = ""
    while time.time() < deadline:
        last = playwright_snapshot(env)
        if predicate(last):
            return last
        time.sleep(0.4)
    diagnostics = json.dumps(safe_snapshot_diagnostics(last), sort_keys=True)
    raise RuntimeError(f"Playwright did not render {label}; diagnostics={diagnostics}")


def wait_for_memory_page(base_url: str, timeout_sec: int = 60) -> int:
    deadline = time.time() + timeout_sec
    last_status = 0
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/workspace/memory", timeout=10) as response:
                last_status = int(response.status)
        except urllib.error.HTTPError as exc:
            last_status = int(exc.code)
        except (TimeoutError, urllib.error.URLError):
            last_status = 0
        if 200 <= last_status < 400:
            return last_status
        if last_status >= 500:
            raise RuntimeError("Memory workspace page returned a server error; status_5xx=true")
        time.sleep(0.4)
    raise RuntimeError(
        f"Memory workspace page did not become ready; status_5xx={last_status >= 500} status_success=false",
    )


def snapshot_ref(snapshot: str, label: str, control: str) -> str:
    for line in snapshot.splitlines():
        if label in line and control.lower() in line.lower():
            match = re.search(r"\[ref=([^\]]+)\]", line)
            if match:
                return match.group(1)
    raise RuntimeError(f"Playwright ref unavailable for {control} {label}")


def click(env: dict[str, str], ref: str) -> None:
    result = playwright(env, "click", ref)
    if result.returncode != 0:
        raise RuntimeError(f"Playwright click failed: {result.stderr[-300:]}")


def select_option(env: dict[str, str], ref: str, value: str) -> None:
    result = playwright(env, "select", ref, value)
    if result.returncode != 0:
        raise RuntimeError(f"Playwright select failed: {result.stderr[-300:]}")


def load_human_session_state(env: dict[str, str], base_url: str, session_cookie: str) -> None:
    parsed = urllib.parse.urlsplit(base_url)
    if not parsed.hostname or not session_cookie:
        raise RuntimeError("Playwright Human Session state is incomplete")
    state = {
        "cookies": [{
            "name": "agentops_human_session",
            "value": session_cookie,
            "domain": parsed.hostname,
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": parsed.scheme == "https",
            "sameSite": "Strict",
        }],
        "origins": [],
    }
    descriptor, raw_path = tempfile.mkstemp(prefix="agentops-human-browser-state-", suffix=".json")
    state_path = Path(raw_path)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, sort_keys=True)
        loaded = playwright(env, "state-load", str(state_path))
    finally:
        state_path.unlink(missing_ok=True)
    if loaded.returncode != 0:
        raise RuntimeError(f"Playwright state load failed: {loaded.stderr[-300:]}")
    navigated = playwright(env, "goto", f"{base_url}/workspace/memory")
    if navigated.returncode != 0:
        raise RuntimeError(f"Playwright session navigation failed: {navigated.stderr[-300:]}")


def layout_contract_ok(env: dict[str, str]) -> bool:
    expression = r"""(() => {
      const groups = [...document.querySelectorAll('.humanSessionBar,.rowActions')];
      const noOverflow = document.documentElement.scrollWidth <= window.innerWidth + 1;
      const controlsFit = [...document.querySelectorAll('.humanSessionBar button,.humanSessionBar input,.humanSessionBar select,.rowActions button')]
        .every((element) => element.scrollWidth <= element.clientWidth + 1);
      const noDirectOverlap = groups.every((group) => {
        const rects = [...group.children].filter((element) => getComputedStyle(element).display !== 'none')
          .map((element) => element.getBoundingClientRect()).filter((rect) => rect.width > 0 && rect.height > 0);
        return rects.every((left, index) => rects.slice(index + 1).every((right) =>
          left.right <= right.left || right.right <= left.left || left.bottom <= right.top || right.bottom <= left.top));
      });
      return noOverflow && controlsFit && noDirectOverlap ? 'AGENTOPS_LAYOUT_OK' : 'AGENTOPS_LAYOUT_FAIL';
    })()"""
    result = playwright(env, "eval", expression)
    return result.returncode == 0 and "AGENTOPS_LAYOUT_OK" in (result.stdout + result.stderr)


def start_safe_proxy_readback() -> tuple[ThreadingHTTPServer, Thread, list[dict[str, bool]]]:
    observations: list[dict[str, bool]] = []

    class Handler(BaseHTTPRequestHandler):
        def handle_request(self) -> None:
            raw_cookie = str(self.headers.get("Cookie") or "")
            observations.append({
                "human_cookie_received": "agentops_human_session=" in raw_cookie,
                "compatibility_cookie_received": "theme=dark" in raw_cookie,
                "authorization_received": str(self.headers.get("Authorization") or "").startswith("Bearer "),
            })
            content_length = int(self.headers.get("Content-Length") or 0)
            if content_length:
                self.rfile.read(content_length)
            payload = json.dumps({
                "ok": True,
                "human_cookie_received": observations[-1]["human_cookie_received"],
                "compatibility_cookie_received": observations[-1]["compatibility_cookie_received"],
                "authorization_received": observations[-1]["authorization_received"],
                "credential_values_omitted": True,
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "agentops_human_session=upstream-confusion; Path=/; HttpOnly")
            self.send_header("Set-Cookie", "legacy_pref=ok; Path=/; SameSite=Lax")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            self.handle_request()

        def do_POST(self) -> None:  # noqa: N802
            self.handle_request()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, observations


def password_material(password: str, salt: bytes) -> tuple[str, str, str]:
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16_384, r=8, p=1, dklen=32)
    params = json.dumps({"name": "scrypt", "n": 16_384, "r": 8, "p": 1, "keylen": 32}, sort_keys=True)
    return derived.hex(), salt.hex(), params


def seed(adapter: PostgresAdapter, passwords: dict[str, str]) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for user_id, (username, membership_role) in USERS.items():
        adapter.execute(
            "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
            (user_id, user_id, f"{username}@example.invalid", "customer", now),
        )
        password_hash, password_salt, params = password_material(passwords[user_id], secrets.token_bytes(16))
        adapter.execute(
            """INSERT INTO human_login_credentials(
                credential_id,user_id,username,password_hash,password_salt,password_params_json,status,
                created_at,updated_at,last_login_at
            ) VALUES(?,?,?,?,?,?,'active',?,?,NULL)""",
            (f"hcred_{username}", user_id, username, password_hash, password_salt, params, now, now),
        )
        if user_id == DISABLED_USER:
            adapter.execute(
                "UPDATE human_login_credentials SET status='disabled' WHERE user_id=?",
                (user_id,),
            )
        adapter.execute(
            """INSERT INTO workspace_memberships(workspace_id,user_id,role,status,created_at,updated_at)
            VALUES(?,?,?,'active',?,?)""",
            (WORKSPACE_ID, user_id, membership_role, now, now),
        )
    adapter.execute(
        """INSERT INTO workspace_memberships(workspace_id,user_id,role,status,created_at,updated_at)
        VALUES(?,?,'viewer','active',?,?)""",
        (OTHER_WORKSPACE_ID, APPROVER_A, now, now),
    )
    adapter.execute(
        """INSERT INTO runtime_connectors(
            runtime_connector_id,provider,connector_type,profile_name,base_url,binary_path,status,allow_real_run,
            require_confirm_run,trust_status,trust_note,trust_updated_at,last_health_at,last_error,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "rtc_agent_gateway_local", "agent_gateway", "local", "Human review smoke", None, None,
            "ready", 0, 1, "trusted", None, now, now, None, now, now,
        ),
    )
    main_memories = [
        MEM_APPROVE,
        MEM_REJECT,
        MEM_SAME_KEY,
        MEM_SINGLE_WINNER,
        MEM_SESSION_RACE,
        MEM_MEMBERSHIP_RACE,
        MEM_OPERATOR,
    ]
    for memory_id in main_memories:
        adapter.execute(
            """INSERT INTO memories(
                memory_id,workspace_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,
                task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,
                supersedes_memory_id,access_tags,created_at,updated_at
            ) VALUES(?,?,'project','project_context',?,'manual',NULL,NULL,NULL,NULL,1.0,'candidate',NULL,NULL,NULL,'[]',?,?)""",
            (memory_id, WORKSPACE_ID, f"Synthetic candidate fixture for {memory_id}.", now, now),
        )
    adapter.execute(
        """INSERT INTO memories(
            memory_id,workspace_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,
            task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,
            supersedes_memory_id,access_tags,created_at,updated_at
        ) VALUES(?,?,'project','project_context',?,'manual',NULL,NULL,NULL,NULL,1.0,'candidate',NULL,NULL,NULL,'[]',?,?)""",
        (MEM_FOREIGN, OTHER_WORKSPACE_ID, "Synthetic foreign tenant fixture.", now, now),
    )
    adapter.commit()


def raw_cookie(headers: dict[str, str]) -> str:
    value = headers.get("set-cookie", "")
    prefix = "agentops_human_session="
    for part in value.split(";"):
        item = part.strip()
        if item.startswith(prefix):
            return item[len(prefix):]
    return ""


def session_hash(key: str, token: str) -> str:
    return hmac.new(key.encode("utf-8"), f"session:{token}".encode("utf-8"), hashlib.sha256).hexdigest()


def login(
    base_url: str,
    username: str,
    password: str,
    *,
    origin: str,
    host: str | None = None,
) -> tuple[int, dict[str, Any], dict[str, str], str]:
    headers = {"Origin": origin}
    if host:
        headers["Host"] = host
    status, payload, response_headers = http_json(
        "POST",
        f"{base_url}/api/mis/human-auth/login",
        {"username": username, "password": password},
        headers=headers,
    )
    return status, payload, response_headers, raw_cookie(response_headers)


def review_headers(origin: str, cookie: str, csrf: str, key: str) -> dict[str, str]:
    return {
        "Origin": origin,
        "Cookie": f"agentops_human_session={cookie}",
        "X-AgentOps-CSRF": csrf,
        "X-AgentOps-Workspace-Id": WORKSPACE_ID,
        "Idempotency-Key": key,
    }


def review(
    base_url: str,
    memory_id: str,
    decision: str,
    origin: str,
    cookie: str,
    csrf: str,
    key: str,
    *,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    headers = review_headers(origin, cookie, csrf, key)
    headers.update(extra_headers or {})
    return http_json(
        "POST",
        f"{base_url}/api/mis/memories/{urllib.parse.quote(memory_id)}/{decision}",
        {"workspace_id": WORKSPACE_ID},
        headers=headers,
    )


def evidence_counts(adapter: PostgresAdapter, memory_id: str) -> tuple[int, int, int]:
    requests = int(adapter.fetchone(
        "SELECT COUNT(*) AS count FROM human_memory_review_requests WHERE workspace_id=? AND memory_id=?",
        (WORKSPACE_ID, memory_id),
    )["count"])
    audits = int(adapter.fetchone(
        "SELECT COUNT(*) AS count FROM audit_logs WHERE entity_type='memories' AND entity_id=?",
        (memory_id,),
    )["count"])
    events = int(adapter.fetchone(
        "SELECT COUNT(*) AS count FROM runtime_events WHERE event_type IN ('memory.approved','memory.rejected')",
    )["count"])
    adapter.commit()
    return requests, audits, events


def run_owner_bootstrap(
    npm_binary: str,
    runtime_dsn: str,
    password: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({
        "AGENTOPS_POSTGRES_DSN": runtime_dsn,
        "AGENTOPS_POSTGRES_SSL": "0",
    })
    return subprocess.run(
        [
            npm_binary,
            "run",
            "--silent",
            "bootstrap:owner",
            "--",
            "--workspace-id",
            WORKSPACE_ID,
            "--username",
            "bootstrap-owner",
            "--display-name",
            "Bootstrap Owner",
            "--password-stdin",
        ],
        cwd=NEXT_APP,
        env=env,
        input=f"{password}\n",
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )


def run_schema_command(
    npm_binary: str,
    runtime_dsn: str,
    *,
    check_only: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({
        "AGENTOPS_POSTGRES_DSN": runtime_dsn,
        "AGENTOPS_POSTGRES_SSL": "0",
    })
    command = "schema:readiness" if check_only else "migrate:postgres"
    return subprocess.run(
        [npm_binary, "run", "--silent", command],
        cwd=NEXT_APP,
        env=env,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )


def run_schema_contract(npm_binary: str, runtime_dsn: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({
        "AGENTOPS_POSTGRES_DSN": runtime_dsn,
        "AGENTOPS_POSTGRES_SSL": "0",
    })
    return subprocess.run(
        [npm_binary, "run", "--silent", "test:human-schema-contract"],
        cwd=NEXT_APP,
        env=env,
        text=True,
        capture_output=True,
        timeout=45,
        check=False,
    )


def has_button(snapshot: str, label: str) -> bool:
    return any(label in line and "button" in line.lower() for line in snapshot.splitlines())


def run_memory_ui_smoke(
    base_url: str,
    adapter: PostgresAdapter,
    bootstrap_user_id: str,
    bootstrap_password: str,
    operator_password: str,
    env: dict[str, str],
) -> tuple[bool, dict[str, str]]:
    existing_sessions = {
        row["session_id"]
        for row in adapter.fetchall(
            "SELECT session_id FROM human_sessions WHERE user_id IN (?,?)",
            (OPERATOR, bootstrap_user_id),
        )
    }
    adapter.commit()
    operator_status, operator_payload, _, operator_cookie = login(
        base_url,
        USERS[OPERATOR][0],
        operator_password,
        origin=base_url,
    )
    if operator_status != 200:
        raise RuntimeError(
            f"Operator Human Session login failed; status={operator_status} "
            f"error={operator_payload.get('error', 'unknown')}"
        )
    owner_status, owner_payload, _, owner_cookie = login(
        base_url,
        "bootstrap-owner",
        bootstrap_password,
        origin=base_url,
    )
    if owner_status != 200:
        raise RuntimeError(
            f"Owner Human Session login failed; status={owner_status} "
            f"error={owner_payload.get('error', 'unknown')}"
        )

    opened = playwright(env, "open", f"{base_url}/workspace/memory", timeout=180)
    if opened.returncode != 0:
        raise RuntimeError(f"Playwright open failed: {opened.stderr[-300:]}")
    resized = playwright(env, "resize", "1365", "900")
    if resized.returncode != 0:
        raise RuntimeError(f"Playwright desktop resize failed: {resized.stderr[-300:]}")

    sign_in = wait_for_snapshot(
        env,
        lambda text: has_button(text, "Sign in"),
        "Human Session sign-in",
        timeout_sec=60,
    )
    load_human_session_state(env, base_url, operator_cookie)
    operator_view = wait_for_snapshot(
        env,
        lambda text: WORKSPACE_ID in text and "Synthetic candidate fixture" in text,
        "operator workspace candidate list",
    )
    operator_controls_hidden = not has_button(operator_view, "Approve") and not has_button(operator_view, "Reject")
    click(env, snapshot_ref(operator_view, "Sign out", "button"))
    signed_out = wait_for_snapshot(env, lambda text: has_button(text, "Sign in"), "operator logout")

    load_human_session_state(env, base_url, owner_cookie)
    owner_workspace_view = wait_for_snapshot(
        env,
        lambda text: "Select workspace" in text and "combobox" in text.lower(),
        "Owner explicit workspace selection",
    )
    select_option(
        env,
        snapshot_ref(owner_workspace_view, "Workspace", "combobox"),
        WORKSPACE_ID,
    )
    owner_view = wait_for_snapshot(
        env,
        lambda text: WORKSPACE_ID in text and has_button(text, "Approve"),
        "Owner candidate review controls",
    )
    desktop_layout_ok = layout_contract_ok(env)
    mobile_resize = playwright(env, "resize", "390", "844")
    if mobile_resize.returncode != 0:
        raise RuntimeError(f"Playwright mobile resize failed: {mobile_resize.stderr[-300:]}")
    mobile_view = wait_for_snapshot(
        env,
        lambda text: WORKSPACE_ID in text and has_button(text, "Approve"),
        "mobile Owner candidate review controls",
    )
    mobile_layout_ok = layout_contract_ok(env)
    desktop_resize = playwright(env, "resize", "1365", "900")
    if desktop_resize.returncode != 0:
        raise RuntimeError(f"Playwright desktop restore failed: {desktop_resize.stderr[-300:]}")
    owner_view = wait_for_snapshot(env, lambda text: has_button(text, "Approve"), "restored Owner review controls")
    click(env, snapshot_ref(owner_view, "Approve", "button"))
    reviewed_memory_id = ""
    deadline = time.time() + 15
    while time.time() < deadline:
        reviewed = adapter.fetchone(
            "SELECT memory_id FROM memories WHERE workspace_id=? AND owner_user_id=? AND review_status='approved'",
            (WORKSPACE_ID, bootstrap_user_id),
        )
        adapter.commit()
        if reviewed:
            reviewed_memory_id = str(reviewed["memory_id"])
            break
        time.sleep(0.4)
    owner_after = playwright_snapshot(env)
    click(env, snapshot_ref(owner_after, "Sign out", "button"))
    final_view = wait_for_snapshot(env, lambda text: has_button(text, "Sign in"), "Owner logout")
    session_rows = adapter.fetchall(
        "SELECT session_id,status FROM human_sessions WHERE user_id IN (?,?) ORDER BY created_at",
        (OPERATOR, bootstrap_user_id),
    )
    adapter.commit()
    ui_sessions = [row for row in session_rows if row["session_id"] not in existing_sessions]
    return (
        operator_controls_hidden
        and desktop_layout_ok
        and mobile_layout_ok
        and has_button(mobile_view, "Approve")
        and bool(reviewed_memory_id)
        and has_button(final_view, "Sign in")
        and len(ui_sessions) == 2
        and all(row["status"] == "revoked" for row in ui_sessions),
        {
            "reviewed_memory_id": reviewed_memory_id,
            "operator_role_controls": "hidden" if operator_controls_hidden else "visible",
            "desktop_layout": "pass" if desktop_layout_ok else "fail",
            "mobile_layout": "pass" if mobile_layout_ok else "fail",
            "logout_state": "revoked" if len(ui_sessions) == 2 and all(row["status"] == "revoked" for row in ui_sessions) else "invalid",
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Next.js/Postgres Human Session Memory Review smoke.")
    parser.add_argument("--image", default=container_smoke.DEFAULT_IMAGE)
    parser.add_argument("--postgres-dsn", default="", help="Use an external Postgres URL in an isolated temporary schema.")
    parser.add_argument("--skip-if-unavailable", action="store_true")
    parser.add_argument("--no-install-driver", action="store_true")
    args = parser.parse_args()

    reexec_self_with_bundled_python_if_needed()
    if not args.postgres_dsn:
        early = container_smoke.docker_available(args.skip_if_unavailable)
        if early is not None:
            return early
        early = container_smoke.ensure_image(args.image, args.skip_if_unavailable)
        if early is not None:
            return early
    if not (NEXT_APP / "node_modules" / "next").exists():
        return unavailable("ui/next-app Node dependencies are required", skip=args.skip_if_unavailable)
    node_binary = shutil.which("node")
    if not node_binary:
        return unavailable("node is required", skip=args.skip_if_unavailable)
    npm_binary = shutil.which("npm")
    if not npm_binary:
        return unavailable("npm is required", skip=args.skip_if_unavailable)
    if not PWCLI.exists():
        return unavailable("Codex Playwright CLI wrapper is required", skip=args.skip_if_unavailable)

    with tempfile.TemporaryDirectory(prefix="agentops-human-review-pg-") as temp_dir:
        driver_ok, driver_status = ensure_psycopg(Path(temp_dir), install=not args.no_install_driver)
        if not driver_ok:
            return unavailable(f"Optional psycopg driver unavailable: {driver_status}", skip=args.skip_if_unavailable)

        container = f"agentops-human-review-pg-{secrets.token_hex(6)}" if not args.postgres_dsn else ""
        pg_secret = secrets.token_urlsafe(18)
        hmac_key = secrets.token_urlsafe(48)
        bootstrap_password = f"Bootstrap-{secrets.token_urlsafe(18)}"
        passwords = {user_id: f"Review-{secrets.token_urlsafe(18)}" for user_id in USERS}
        sensitive = [pg_secret, hmac_key, bootstrap_password, *passwords.values()]
        if args.postgres_dsn:
            sensitive.append(args.postgres_dsn)
        base_dsn = args.postgres_dsn
        runtime_dsn = ""
        schema = f"agentops_human_review_{secrets.token_hex(8)}"
        next_proc: subprocess.Popen[str] | None = None
        proxy_proc: subprocess.Popen[str] | None = None
        fake_upstream: ThreadingHTTPServer | None = None
        fake_upstream_thread: Thread | None = None
        adapter: PostgresAdapter | None = None
        setup_adapter: PostgresAdapter | None = None
        blockers: list[PostgresAdapter] = []
        pw_env: dict[str, str] | None = None
        checks: dict[str, bool] = {}
        failures: list[str] = []
        production_proxy_diagnostics: dict[str, Any] = {}
        try:
            if not base_dsn:
                started = container_smoke.run([
                    "docker", "run", "-d", "--rm", "--name", container,
                    "-p", "127.0.0.1::5432",
                    "-e", "POSTGRES_USER=agentops",
                    "-e", "POSTGRES_DB=agentops",
                    "-e", f"POSTGRES_PASSWORD={pg_secret}",
                    args.image,
                ], timeout=60)
                if started.returncode != 0:
                    return unavailable(
                        started.stderr or started.stdout or "Postgres container failed to start",
                        skip=args.skip_if_unavailable,
                        sensitive=sensitive,
                    )
                if not container_smoke.wait_for_postgres(container):
                    raise RuntimeError("Postgres container did not become ready")
                base_dsn = f"postgresql://agentops:{pg_secret}@127.0.0.1:{mapped_port(container)}/agentops"
                sensitive.append(base_dsn)

            setup_adapter = connect_postgres_when_ready(base_dsn, secret=pg_secret)
            setup_adapter.execute(f'CREATE SCHEMA "{schema}"')
            setup_adapter.commit()
            setup_adapter.close()
            setup_adapter = None
            runtime_dsn = dsn_with_search_path(base_dsn, schema)
            sensitive.append(runtime_dsn)

            adapter = connect_postgres_when_ready(runtime_dsn, secret=pg_secret)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            adapter.commit()
            first_migration = run_schema_command(npm_binary, runtime_dsn)
            second_migration = run_schema_command(npm_binary, runtime_dsn)
            schema_readiness = run_schema_command(npm_binary, runtime_dsn, check_only=True)
            schema_contract = run_schema_contract(npm_binary, runtime_dsn)
            first_migration_payload = json.loads(first_migration.stdout or "{}")
            second_migration_payload = json.loads(second_migration.stdout or "{}")
            schema_readiness_payload = json.loads(schema_readiness.stdout or "{}")
            schema_contract_payload = json.loads(schema_contract.stdout or "{}")
            schema_version = adapter.fetchone(
                """SELECT component,version,schema_contract FROM agentops_schema_migrations
                WHERE component='human_session_memory_review'"""
            )
            adapter.commit()
            check(
                checks,
                failures,
                "node_postgres_migration_runner_is_idempotent_and_exact_ready",
                first_migration.returncode == 0
                and second_migration.returncode == 0
                and schema_readiness.returncode == 0
                and schema_contract.returncode == 0
                and first_migration_payload.get("ready") is True
                and second_migration_payload.get("ready") is True
                and schema_readiness_payload.get("operation") == "commercial_schema_readiness"
                and schema_readiness_payload.get("ready") is True
                and schema_contract_payload.get("contract") == "human_memory_schema_readiness_v5"
                and all((schema_contract_payload.get("checks") or {}).values())
                and schema_version is not None
                and schema_version["version"] == CURRENT_SCHEMA_VERSION
                and schema_version["schema_contract"] == CURRENT_SCHEMA_CONTRACT,
            )

            scrypt_contract = subprocess.run(
                [npm_binary, "run", "--silent", "test:human-scrypt-contract"],
                cwd=NEXT_APP,
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
            scrypt_payload = json.loads((scrypt_contract.stdout or "{}").splitlines()[-1])
            first_bootstrap = run_owner_bootstrap(npm_binary, runtime_dsn, bootstrap_password)
            second_bootstrap = run_owner_bootstrap(npm_binary, runtime_dsn, bootstrap_password)
            first_bootstrap_payload = json.loads(first_bootstrap.stdout or "{}")
            second_bootstrap_payload = json.loads(second_bootstrap.stdout or "{}")
            owner_row = adapter.fetchone(
                """SELECT users.user_id,users.name,membership.workspace_id,membership.role,membership.status,
                credential.username,credential.password_hash,credential.password_salt,credential.password_params_json
                FROM workspace_memberships membership
                JOIN users ON users.user_id=membership.user_id
                JOIN human_login_credentials credential ON credential.user_id=users.user_id
                WHERE membership.role='owner'"""
            )
            owner_audit = adapter.fetchone(
                """SELECT actor_type,actor_id,action,entity_type,entity_id,metadata_json
                FROM audit_logs WHERE action='human_auth.owner_bootstrap'"""
            )
            owner_count = int(adapter.fetchone(
                "SELECT COUNT(*) AS count FROM workspace_memberships WHERE role='owner'"
            )["count"])
            adapter.commit()
            owner_params = json.loads(str((owner_row or {}).get("password_params_json") or "{}"))
            bootstrap_user_id = str(first_bootstrap_payload.get("user", {}).get("user_id") or "")
            check(
                checks,
                failures,
                "node_typescript_owner_bootstrap_is_atomic_once_only_and_audited",
                scrypt_contract.returncode == 0
                and scrypt_payload.get("ok") is True
                and scrypt_payload.get("scrypt_work_count") == 4
                and first_bootstrap.returncode == 0
                and first_bootstrap_payload.get("ok") is True
                and first_bootstrap_payload.get("schema_version") == CURRENT_SCHEMA_VERSION
                and second_bootstrap.returncode != 0
                and second_bootstrap_payload.get("error") == "owner_already_initialized"
                and owner_count == 1
                and owner_row is not None
                and owner_row["user_id"] == bootstrap_user_id
                and owner_row["workspace_id"] == WORKSPACE_ID
                and owner_row["role"] == "owner"
                and owner_row["status"] == "active"
                and owner_row["password_hash"] != bootstrap_password
                and owner_row["password_salt"] != bootstrap_password
                and owner_params == {"name": "scrypt", "n": 16_384, "r": 8, "p": 1, "keylen": 32}
                and owner_audit is not None
                and owner_audit["actor_type"] == "system"
                and owner_audit["actor_id"] is None
                and owner_audit["entity_id"] == bootstrap_user_id
                and bootstrap_password not in json.dumps(owner_audit, default=str),
            )
            seed(adapter, passwords)

            port = free_port()
            base_url = f"http://127.0.0.1:{port}"
            loopback_origin = base_url
            private_origin = "https://private.example.test"
            next_env = os.environ.copy()
            next_env.update({
                "AGENTOPS_DEPLOYMENT_MODE": "production",
                "AGENTOPS_CONTROL_PLANE_MODE": "postgres",
                "AGENTOPS_POSTGRES_DSN": runtime_dsn,
                "AGENTOPS_API_BASE": f"http://127.0.0.1:{free_port()}/api",
                "AGENTOPS_ALLOWED_ORIGINS": f"{loopback_origin},{private_origin}",
                "AGENTOPS_HUMAN_SESSION_HMAC_KEY": hmac_key,
                "AGENTOPS_HUMAN_LOGIN_CONCURRENCY": "1",
                "NEXT_TELEMETRY_DISABLED": "1",
            })
            next_proc = start_process(
                [node_binary, str(NEXT_APP / "node_modules" / "next" / "dist" / "bin" / "next"), "dev", "-p", str(port)],
                cwd=NEXT_APP,
                env=next_env,
            )
            wait_for_next(base_url, next_proc, sensitive)

            sessions_before = int(adapter.fetchone("SELECT COUNT(*) AS count FROM human_sessions")["count"])
            throttle_before = int(adapter.fetchone("SELECT COUNT(*) AS count FROM human_login_throttle")["count"])
            adapter.commit()
            oversized_login_status, _, _ = http_json(
                "POST",
                f"{base_url}/api/mis/human-auth/login",
                raw_body=b"{" + (b"x" * (9 * 1024)) + b"}",
                headers={"Origin": loopback_origin},
            )
            oversized_review_status, _, _ = http_json(
                "POST",
                f"{base_url}/api/mis/memories/{MEM_APPROVE}/approve",
                raw_body=b"{" + (b"x" * (9 * 1024)) + b"}",
                headers={"Origin": loopback_origin},
            )
            chunked_login = node_chunked_probe(
                node_binary,
                f"{base_url}/api/mis/human-auth/login",
                9 * 1024,
                {"Origin": loopback_origin},
            )
            chunked_logout = node_chunked_probe(
                node_binary,
                f"{base_url}/api/mis/human-auth/logout",
                2 * 1024,
                {"Origin": loopback_origin},
            )
            chunked_review = node_chunked_probe(
                node_binary,
                f"{base_url}/api/mis/memories/{MEM_APPROVE}/approve",
                9 * 1024,
                {"Origin": loopback_origin},
            )
            sessions_after = int(adapter.fetchone("SELECT COUNT(*) AS count FROM human_sessions")["count"])
            throttle_after = int(adapter.fetchone("SELECT COUNT(*) AS count FROM human_login_throttle")["count"])
            adapter.commit()
            check(
                checks,
                failures,
                "body_bounds_before_auth_and_db",
                oversized_login_status == 413
                and oversized_review_status == 413
                and all(
                    probe.get("status") == 413
                    and probe.get("error") == "request_too_large"
                    and probe.get("content_length_sent") is False
                    for probe in [chunked_login, chunked_logout, chunked_review]
                )
                and sessions_before == sessions_after
                and throttle_before == throttle_after,
            )

            stale_at = "2000-01-01T00:00:00+00:00"
            adapter.execute(
                """INSERT INTO human_login_throttle(
                    bucket_key,failure_count,window_started_at,blocked_until,updated_at
                ) VALUES(?,1,?,NULL,?)""",
                ("stale-admission-fixture", stale_at, stale_at),
            )
            adapter.commit()
            admission_blocker = connect_postgres_when_ready(runtime_dsn, secret=pg_secret)
            blockers.append(admission_blocker)
            admission_blocker.execute("BEGIN")
            admission_blocker.execute(
                "SELECT credential_id FROM human_login_credentials WHERE username=? FOR UPDATE",
                (USERS[APPROVER_A][0],),
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                admitted_future = executor.submit(
                    login,
                    base_url,
                    USERS[APPROVER_A][0],
                    passwords[APPROVER_A],
                    origin=loopback_origin,
                )
                lock_wait_seen = False
                lock_deadline = time.time() + 10
                while time.time() < lock_deadline:
                    waiting = int(adapter.fetchone(
                        """SELECT COUNT(*) AS count FROM pg_stat_activity
                        WHERE datname=current_database()
                          AND application_name='agentops-mis-typescript-control-plane'
                          AND wait_event_type='Lock'"""
                    )["count"])
                    adapter.commit()
                    if waiting > 0:
                        lock_wait_seen = True
                        break
                    time.sleep(0.1)
                saturated_status, saturated_payload, _, _ = login(
                    base_url,
                    "rotated-attacker-subject",
                    "Wrong-password-value",
                    origin=loopback_origin,
                )
                admission_blocker.rollback()
                admission_blocker.close()
                blockers.remove(admission_blocker)
                admitted_status, admitted_payload, _, admitted_cookie = admitted_future.result(timeout=20)
            stale_remaining = int(adapter.fetchone(
                "SELECT COUNT(*) AS count FROM human_login_throttle WHERE bucket_key='stale-admission-fixture'"
            )["count"])
            saturated_subject_rows = int(adapter.fetchone(
                "SELECT COUNT(*) AS count FROM human_login_throttle"
            )["count"])
            adapter.commit()
            admission_logout_status, _, _ = http_json(
                "POST",
                f"{base_url}/api/mis/human-auth/logout",
                {},
                headers={
                    "Origin": loopback_origin,
                    "Cookie": f"agentops_human_session={admitted_cookie}",
                    "X-AgentOps-CSRF": str(admitted_payload.get("csrf_token") or ""),
                },
            )
            check(
                checks,
                failures,
                "login_admission_is_pre_db_bounded_released_and_cleans_stale_throttle",
                lock_wait_seen
                and saturated_status == 429
                and saturated_payload.get("error") == "human_login_capacity_exceeded"
                and admitted_status == 200
                and admission_logout_status == 200
                and stale_remaining == 0
                and saturated_subject_rows == 0,
            )

            fallback_before = adapter.fetchone(
                "SELECT review_status,owner_user_id FROM memories WHERE memory_id=?",
                (MEM_APPROVE,),
            )
            adapter.commit()
            fallback_status, fallback_payload, _ = http_json(
                "POST",
                f"{base_url}/workspace/memory/review",
                raw_body=b"memory_id=mem_human_approve&decision=approve",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": loopback_origin,
                },
            )
            fallback_after = adapter.fetchone(
                "SELECT review_status,owner_user_id FROM memories WHERE memory_id=?",
                (MEM_APPROVE,),
            )
            adapter.commit()
            check(
                checks,
                failures,
                "postgres_form_fallback_is_fail_closed_without_python",
                fallback_status == 503
                and fallback_payload.get("error") == "typescript_route_owner_required"
                and fallback_payload.get("python_proxy_performed") is False
                and fallback_before == fallback_after,
            )

            bad_origin_status, bad_origin_payload, _, _ = login(
                base_url, USERS[APPROVER_A][0], passwords[APPROVER_A], origin="https://evil.example.test"
            )
            check(
                checks,
                failures,
                "strict_origin_rejected",
                bad_origin_status == 403 and bad_origin_payload.get("error") == "origin_validation_failed",
            )
            wrong_status, wrong_payload, _, _ = login(
                base_url, USERS[APPROVER_A][0], "Wrong-password-value", origin=loopback_origin
            )
            unknown_status, unknown_payload, _, _ = login(
                base_url, "unknown-user", "Wrong-password-value", origin=loopback_origin
            )
            invalid_status, invalid_payload, _, _ = login(
                base_url, "!!", "Wrong-password-value", origin=loopback_origin
            )
            disabled_status, disabled_payload, _, _ = login(
                base_url, USERS[DISABLED_USER][0], passwords[DISABLED_USER], origin=loopback_origin
            )
            committed_throttle_rows = int(adapter.fetchone(
                "SELECT COUNT(*) AS count FROM human_login_throttle"
            )["count"])
            adapter.commit()
            check(
                checks,
                failures,
                "invalid_unknown_disabled_login_is_same_shape_with_scrypt_work",
                wrong_status == 401
                and wrong_payload.get("error") == "invalid_credentials"
                and USERS[APPROVER_A][0] not in json.dumps(wrong_payload)
                and unknown_status == 401
                and invalid_status == 401
                and disabled_status == 401
                and wrong_payload == unknown_payload == invalid_payload == disabled_payload
                and scrypt_payload.get("ok") is True
                and scrypt_payload.get("attempts") == scrypt_payload.get("scrypt_work_count")
                and committed_throttle_rows == 4,
            )

            status_a, payload_a, headers_a, cookie_a = login(
                base_url, USERS[APPROVER_A][0], passwords[APPROVER_A], origin=loopback_origin
            )
            csrf_a = str(payload_a.get("csrf_token") or "")
            cookie_header_a = headers_a.get("set-cookie", "")
            stored_a = adapter.fetchone(
                "SELECT session_id,session_hash,status FROM human_sessions WHERE session_hash=?",
                (session_hash(hmac_key, cookie_a),),
            )
            login_audits = adapter.fetchall(
                "SELECT workspace_id FROM audit_logs "
                "WHERE action='human_auth.login' AND actor_id=? "
                "ORDER BY created_at DESC,audit_id DESC LIMIT 2",
                (APPROVER_A,),
            )
            adapter.commit()
            check(
                checks,
                failures,
                "loopback_cookie_hash_and_csrf",
                status_a == 200
                and bool(cookie_a)
                and bool(csrf_a)
                and stored_a is not None
                and stored_a["session_hash"] != cookie_a
                and "HttpOnly" in cookie_header_a
                and "SameSite=Strict" in cookie_header_a
                and "Secure" not in cookie_header_a
                and any(
                    membership.get("workspace_id") == WORKSPACE_ID
                    and membership.get("role") == "approver"
                    for membership in payload_a.get("memberships", [])
                )
                and {row["workspace_id"] for row in login_audits} == {WORKSPACE_ID, OTHER_WORKSPACE_ID}
                and passwords[APPROVER_A] not in json.dumps(payload_a),
            )

            secure_status, _, secure_headers, secure_cookie = login(
                base_url,
                USERS[APPROVER_A][0],
                passwords[APPROVER_A],
                origin=private_origin,
                host="private.example.test",
            )
            check(
                checks,
                failures,
                "private_https_cookie_secure",
                secure_status == 200 and bool(secure_cookie) and "Secure" in secure_headers.get("set-cookie", ""),
            )

            session_status, session_payload, _ = http_json(
                "GET",
                f"{base_url}/api/mis/human-auth/session",
                headers={"Cookie": f"agentops_human_session={cookie_a}"},
            )
            memberships = session_payload.get("memberships") or []
            check(
                checks,
                failures,
                "session_memberships_are_multi_workspace",
                session_status == 200
                and {item.get("workspace_id") for item in memberships} == {WORKSPACE_ID, OTHER_WORKSPACE_ID}
                and session_payload.get("csrf_token") == csrf_a,
            )

            machine_status, machine_payload, _ = http_json(
                "GET",
                f"{base_url}/api/mis/human-auth/session",
                headers={
                    "Cookie": f"agentops_human_session={cookie_a}",
                    "Authorization": "Bearer synthetic-machine-credential",
                },
            )
            clean_status, _, _ = http_json(
                "GET",
                f"{base_url}/api/mis/human-auth/session",
                headers={"Cookie": f"agentops_human_session={cookie_a}"},
            )
            admin_status, admin_payload, _ = review(
                base_url,
                MEM_APPROVE,
                "approve",
                loopback_origin,
                cookie_a,
                csrf_a,
                "memory-admin-key-reject-0001",
                extra_headers={"X-AgentOps-Workspace-Admin-Key": "synthetic-admin-key"},
            )
            check(
                checks,
                failures,
                "machine_credentials_rejected_without_human_signout",
                machine_status == 401
                and machine_payload.get("error") == "machine_credential_not_allowed"
                and admin_status == 401
                and admin_payload.get("error") == "machine_credential_not_allowed"
                and clean_status == 200,
            )

            list_status, list_payload, _ = http_json(
                "GET",
                f"{base_url}/api/mis/memories?workspace_id={urllib.parse.quote(WORKSPACE_ID)}",
                headers={"Cookie": f"agentops_human_session={cookie_a}"},
            )
            listed_ids = {row.get("memory_id") for row in list_payload} if isinstance(list_payload, list) else set()
            check(
                checks,
                failures,
                "candidate_list_is_session_and_tenant_scoped",
                list_status == 200 and MEM_APPROVE in listed_ids and MEM_FOREIGN not in listed_ids,
            )

            no_auth_status, no_auth_payload, _ = http_json(
                "POST",
                f"{base_url}/api/mis/memories/{MEM_APPROVE}/approve",
                {"workspace_id": WORKSPACE_ID},
                headers={"Origin": loopback_origin, "Idempotency-Key": "memory-no-auth-denied-0001"},
            )
            bad_csrf_status, bad_csrf_payload, _ = review(
                base_url,
                MEM_APPROVE,
                "approve",
                loopback_origin,
                cookie_a,
                "wrong-csrf",
                "memory-wrong-csrf-0001",
            )
            mismatch_headers = review_headers(loopback_origin, cookie_a, csrf_a, "memory-workspace-mismatch-01")
            mismatch_headers["X-AgentOps-Workspace-Id"] = OTHER_WORKSPACE_ID
            mismatch_status, mismatch_payload, _ = http_json(
                "POST",
                f"{base_url}/api/mis/memories/{MEM_APPROVE}/approve",
                {"workspace_id": WORKSPACE_ID},
                headers=mismatch_headers,
            )
            check(
                checks,
                failures,
                "human_cookie_csrf_workspace_binding",
                no_auth_status == 401
                and no_auth_payload.get("error") == "human_auth_required"
                and bad_csrf_status == 403
                and bad_csrf_payload.get("error") == "csrf_validation_failed"
                and mismatch_status == 403
                and mismatch_payload.get("error") == "forbidden",
            )

            operator_status, operator_payload, _, operator_cookie = login(
                base_url, USERS[OPERATOR][0], passwords[OPERATOR], origin=loopback_origin
            )
            operator_csrf = str(operator_payload.get("csrf_token") or "")
            operator_review_status, operator_review_payload, _ = review(
                base_url,
                MEM_OPERATOR,
                "approve",
                loopback_origin,
                operator_cookie,
                operator_csrf,
                "memory-operator-denied-0001",
            )
            check(
                checks,
                failures,
                "workspace_role_enforced",
                operator_status == 200
                and operator_review_status == 403
                and operator_review_payload.get("error") == "human_role_forbidden",
            )

            foreign_status, foreign_payload, _ = review(
                base_url,
                MEM_FOREIGN,
                "approve",
                loopback_origin,
                cookie_a,
                csrf_a,
                "memory-foreign-oracle-0001",
            )
            missing_status, missing_payload, _ = review(
                base_url,
                MEM_MISSING,
                "approve",
                loopback_origin,
                cookie_a,
                csrf_a,
                "memory-missing-oracle-0001",
            )
            check(
                checks,
                failures,
                "foreign_and_missing_ids_are_identical",
                foreign_status == 404
                and missing_status == 404
                and foreign_payload == missing_payload
                and MEM_FOREIGN not in json.dumps(foreign_payload),
            )

            approve_key = "memory-approve-idempotency-0001"
            approve_status, approve_payload, _ = review(
                base_url, MEM_APPROVE, "approve", loopback_origin, cookie_a, csrf_a, approve_key
            )
            replay_status, replay_payload, _ = review(
                base_url, MEM_APPROVE, "approve", loopback_origin, cookie_a, csrf_a, approve_key
            )
            idem_conflict_status, idem_conflict_payload, _ = review(
                base_url, MEM_APPROVE, "reject", loopback_origin, cookie_a, csrf_a, approve_key
            )
            terminal_status, terminal_payload, _ = review(
                base_url, MEM_APPROVE, "approve", loopback_origin, cookie_a, csrf_a, "memory-second-key-conflict-01"
            )
            approve_row = adapter.fetchone(
                "SELECT review_status,owner_user_id,canonical_text FROM memories WHERE memory_id=?",
                (MEM_APPROVE,),
            )
            approve_requests, approve_audits, approve_events_total = evidence_counts(adapter, MEM_APPROVE)
            approve_audit = adapter.fetchone(
                "SELECT actor_type,actor_id,metadata_json FROM audit_logs WHERE entity_type='memories' AND entity_id=?",
                (MEM_APPROVE,),
            )
            approve_request = adapter.fetchone(
                "SELECT idempotency_key_hash,request_hash,status FROM human_memory_review_requests WHERE memory_id=?",
                (MEM_APPROVE,),
            )
            adapter.commit()
            check(
                checks,
                failures,
                "idempotent_review_and_truthful_evidence",
                approve_status == 200
                and approve_payload.get("outcome") == "updated"
                and replay_status == 200
                and replay_payload.get("outcome") == "unchanged"
                and idem_conflict_status == 409
                and idem_conflict_payload.get("error") == "memory_review_idempotency_conflict"
                and terminal_status == 409
                and terminal_payload.get("error") == "memory_review_conflict"
                and approve_row is not None
                and approve_row["review_status"] == "approved"
                and approve_row["owner_user_id"] == APPROVER_A
                and approve_requests == 1
                and approve_audits == 1
                and approve_audit is not None
                and approve_audit["actor_type"] == "user"
                and approve_audit["actor_id"] == APPROVER_A
                and approve_request is not None
                and approve_request["idempotency_key_hash"] != approve_key
                and "credentials_omitted" in str(approve_audit["metadata_json"]),
            )

            reject_status, reject_payload, _ = review(
                base_url, MEM_REJECT, "reject", loopback_origin, cookie_a, csrf_a, "memory-reject-idempotency-001"
            )
            check(
                checks,
                failures,
                "reject_transition_is_human_governed",
                reject_status == 200
                and reject_payload.get("review_status") == "rejected"
                and reject_payload.get("raw_body_omitted") is True,
            )

            before_same_events = int(adapter.fetchone(
                "SELECT COUNT(*) AS count FROM runtime_events WHERE event_type IN ('memory.approved','memory.rejected')"
            )["count"])
            adapter.commit()
            same_key = "memory-same-key-concurrency-001"
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                same_futures = [
                    executor.submit(
                        review,
                        base_url,
                        MEM_SAME_KEY,
                        "approve",
                        loopback_origin,
                        cookie_a,
                        csrf_a,
                        same_key,
                    )
                    for _ in range(2)
                ]
                same_results = [future.result(timeout=25) for future in same_futures]
            same_requests, same_audits, after_same_events = evidence_counts(adapter, MEM_SAME_KEY)
            check(
                checks,
                failures,
                "same_key_concurrency_replays_one_winner",
                sorted(status for status, _, _ in same_results) == [200, 200]
                and sorted(payload.get("outcome") for _, payload, _ in same_results) == ["unchanged", "updated"]
                and same_requests == 1
                and same_audits == 1
                and after_same_events == before_same_events + 1,
            )

            status_b, payload_b, _, cookie_b = login(
                base_url, USERS[APPROVER_B][0], passwords[APPROVER_B], origin=loopback_origin
            )
            csrf_b = str(payload_b.get("csrf_token") or "")
            before_winner_events = after_same_events
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                winner_futures = [
                    executor.submit(
                        review,
                        base_url,
                        MEM_SINGLE_WINNER,
                        "approve",
                        loopback_origin,
                        cookie_a,
                        csrf_a,
                        "memory-winner-approver-a-001",
                    ),
                    executor.submit(
                        review,
                        base_url,
                        MEM_SINGLE_WINNER,
                        "reject",
                        loopback_origin,
                        cookie_b,
                        csrf_b,
                        "memory-winner-approver-b-001",
                    ),
                ]
                winner_results = [future.result(timeout=25) for future in winner_futures]
            winner_requests, winner_audits, after_winner_events = evidence_counts(adapter, MEM_SINGLE_WINNER)
            winner_row = adapter.fetchone(
                "SELECT review_status,owner_user_id FROM memories WHERE memory_id=?",
                (MEM_SINGLE_WINNER,),
            )
            adapter.commit()
            check(
                checks,
                failures,
                "different_reviewers_have_one_terminal_winner",
                sorted(status for status, _, _ in winner_results) == [200, 409]
                and winner_requests == 1
                and winner_audits == 1
                and after_winner_events == before_winner_events + 1
                and winner_row is not None
                and winner_row["owner_user_id"] in {APPROVER_A, APPROVER_B}
                and winner_row["review_status"] in {"approved", "rejected"},
            )

            session_race_status, session_race_payload, _, session_race_cookie = login(
                base_url,
                USERS[SESSION_RACE_USER][0],
                passwords[SESSION_RACE_USER],
                origin=loopback_origin,
            )
            session_race_csrf = str(session_race_payload.get("csrf_token") or "")
            session_blocker = PostgresAdapter.connect(runtime_dsn)
            blockers.append(session_blocker)
            race_session_id = session_blocker.fetchone(
                "SELECT session_id FROM human_sessions WHERE session_hash=? FOR UPDATE",
                (session_hash(hmac_key, session_race_cookie),),
            )["session_id"]
            session_blocker.execute(
                "UPDATE human_sessions SET status='revoked',revoked_at=? WHERE session_id=?",
                (dt.datetime.now(dt.timezone.utc).isoformat(), race_session_id),
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                pending_session_review = executor.submit(
                    review,
                    base_url,
                    MEM_SESSION_RACE,
                    "approve",
                    loopback_origin,
                    session_race_cookie,
                    session_race_csrf,
                    "memory-session-revoke-race-01",
                )
                time.sleep(0.4)
                session_was_blocked = not pending_session_review.done()
                session_blocker.commit()
                session_race_result = pending_session_review.result(timeout=25)
            session_blocker.close()
            blockers.remove(session_blocker)
            session_race_row = adapter.fetchone(
                "SELECT review_status FROM memories WHERE memory_id=?",
                (MEM_SESSION_RACE,),
            )
            session_race_evidence = evidence_counts(adapter, MEM_SESSION_RACE)
            check(
                checks,
                failures,
                "session_revocation_race_fails_closed",
                session_race_status == 200
                and session_was_blocked
                and session_race_result[0] == 401
                and session_race_result[1].get("error") == "human_session_invalid"
                and session_race_row is not None
                and session_race_row["review_status"] == "candidate"
                and session_race_evidence[0:2] == (0, 0),
            )

            member_race_status, member_race_payload, _, member_race_cookie = login(
                base_url,
                USERS[MEMBERSHIP_RACE_USER][0],
                passwords[MEMBERSHIP_RACE_USER],
                origin=loopback_origin,
            )
            member_race_csrf = str(member_race_payload.get("csrf_token") or "")
            membership_blocker = PostgresAdapter.connect(runtime_dsn)
            blockers.append(membership_blocker)
            membership_blocker.execute(
                "SELECT workspace_id FROM workspace_memberships WHERE workspace_id=? AND user_id=? FOR UPDATE",
                (WORKSPACE_ID, MEMBERSHIP_RACE_USER),
            ).fetchone()
            membership_blocker.execute(
                "UPDATE workspace_memberships SET status='disabled',updated_at=? WHERE workspace_id=? AND user_id=?",
                (dt.datetime.now(dt.timezone.utc).isoformat(), WORKSPACE_ID, MEMBERSHIP_RACE_USER),
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                pending_member_review = executor.submit(
                    review,
                    base_url,
                    MEM_MEMBERSHIP_RACE,
                    "approve",
                    loopback_origin,
                    member_race_cookie,
                    member_race_csrf,
                    "memory-membership-revoke-race-1",
                )
                time.sleep(0.4)
                membership_was_blocked = not pending_member_review.done()
                membership_blocker.commit()
                membership_race_result = pending_member_review.result(timeout=25)
            membership_blocker.close()
            blockers.remove(membership_blocker)
            membership_race_row = adapter.fetchone(
                "SELECT review_status FROM memories WHERE memory_id=?",
                (MEM_MEMBERSHIP_RACE,),
            )
            membership_race_evidence = evidence_counts(adapter, MEM_MEMBERSHIP_RACE)
            check(
                checks,
                failures,
                "membership_revocation_race_fails_closed",
                member_race_status == 200
                and membership_was_blocked
                and membership_race_result[0] == 403
                and membership_race_result[1].get("error") == "human_membership_forbidden"
                and membership_race_row is not None
                and membership_race_row["review_status"] == "candidate"
                and membership_race_evidence[0:2] == (0, 0),
            )

            expired_status, expired_payload, _, expired_cookie = login(
                base_url, USERS[APPROVER_B][0], passwords[APPROVER_B], origin=loopback_origin
            )
            adapter.execute(
                "UPDATE human_sessions SET expires_at=? WHERE session_hash=?",
                (
                    (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).isoformat(),
                    session_hash(hmac_key, expired_cookie),
                ),
            )
            adapter.commit()
            expired_read_status, expired_read_payload, _ = http_json(
                "GET",
                f"{base_url}/api/mis/human-auth/session",
                headers={"Cookie": f"agentops_human_session={expired_cookie}"},
            )
            expired_row = adapter.fetchone(
                "SELECT status FROM human_sessions WHERE session_hash=?",
                (session_hash(hmac_key, expired_cookie),),
            )
            adapter.commit()
            check(
                checks,
                failures,
                "session_expiry_is_committed_and_rejected",
                expired_status == 200
                and expired_read_status == 401
                and expired_read_payload.get("error") == "human_session_expired"
                and expired_row is not None
                and expired_row["status"] == "expired",
            )

            wrong_logout_status, wrong_logout_payload, _ = http_json(
                "POST",
                f"{base_url}/api/mis/human-auth/logout",
                {},
                headers={
                    "Origin": loopback_origin,
                    "Cookie": f"agentops_human_session={cookie_a}",
                    "X-AgentOps-CSRF": "wrong-csrf",
                },
            )
            still_active_status, _, _ = http_json(
                "GET",
                f"{base_url}/api/mis/human-auth/session",
                headers={"Cookie": f"agentops_human_session={cookie_a}"},
            )
            logout_status, logout_payload, logout_headers = http_json(
                "POST",
                f"{base_url}/api/mis/human-auth/logout",
                {},
                headers={
                    "Origin": loopback_origin,
                    "Cookie": f"agentops_human_session={cookie_a}",
                    "X-AgentOps-CSRF": csrf_a,
                    "X-AgentOps-Workspace-Id": WORKSPACE_ID,
                },
            )
            post_logout_status, post_logout_payload, _ = http_json(
                "GET",
                f"{base_url}/api/mis/human-auth/session",
                headers={"Cookie": f"agentops_human_session={cookie_a}"},
            )
            logout_audits = adapter.fetchall(
                "SELECT workspace_id FROM audit_logs "
                "WHERE action='human_auth.logout' AND actor_id=? "
                "ORDER BY created_at DESC,audit_id DESC LIMIT 2",
                (APPROVER_A,),
            )
            adapter.commit()
            check(
                checks,
                failures,
                "logout_requires_csrf_and_revokes",
                wrong_logout_status == 403
                and wrong_logout_payload.get("error") == "csrf_validation_failed"
                and still_active_status == 200
                and logout_status == 200
                and logout_payload.get("authenticated") is False
                and "Max-Age=0" in logout_headers.get("set-cookie", "")
                and post_logout_status == 401
                and post_logout_payload.get("error") == "human_session_invalid"
                and {row["workspace_id"] for row in logout_audits} == {WORKSPACE_ID, OTHER_WORKSPACE_ID},
            )

            safe_auth_responses = json.dumps([
                payload_a,
                session_payload,
            ], sort_keys=True)
            safe_mutation_responses = json.dumps([
                approve_payload,
                replay_payload,
                reject_payload,
                *[payload for _, payload, _ in same_results],
                *[payload for _, payload, _ in winner_results],
            ], sort_keys=True)
            safe_responses = safe_auth_responses + safe_mutation_responses
            safe_db = json.dumps({
                "audit": approve_audit,
                "request": approve_request,
                "session": stored_a,
            }, sort_keys=True, default=str)
            check(
                checks,
                failures,
                "credentials_and_raw_body_are_omitted",
                all(value not in safe_responses and value not in safe_db for value in [
                    hmac_key,
                    bootstrap_password,
                    *passwords.values(),
                    cookie_a,
                ])
                and all(value not in safe_mutation_responses and value not in safe_db for value in [
                    csrf_a,
                    approve_key,
                ])
                and "password" not in safe_responses.lower()
                and approve_events_total == 1,
            )

            pw_env = os.environ.copy()
            pw_env["PLAYWRIGHT_CLI_SESSION"] = f"human-review-{secrets.token_hex(6)}"
            memory_page_status = wait_for_memory_page(base_url)
            check(
                checks,
                failures,
                "memory_workspace_page_is_not_500",
                200 <= memory_page_status < 400,
            )
            ui_ok, ui_evidence = run_memory_ui_smoke(
                base_url,
                adapter,
                bootstrap_user_id,
                bootstrap_password,
                passwords[OPERATOR],
                pw_env,
            )
            check(
                checks,
                failures,
                "browser_session_workspace_role_review_logout_desktop_mobile",
                ui_ok
                and ui_evidence.get("operator_role_controls") == "hidden"
                and ui_evidence.get("desktop_layout") == "pass"
                and ui_evidence.get("mobile_layout") == "pass"
                and ui_evidence.get("logout_state") == "revoked",
            )

            playwright(pw_env, "close", timeout=30)
            pw_env = None
            stop_process(next_proc)
            next_proc = None
            fake_upstream, fake_upstream_thread, proxy_observations = start_safe_proxy_readback()
            proxy_port = free_port()
            proxy_base_url = f"http://127.0.0.1:{proxy_port}"
            proxy_env = os.environ.copy()
            proxy_env.update({
                "AGENTOPS_DEPLOYMENT_MODE": "production",
                "AGENTOPS_CONTROL_PLANE_MODE": "proxy",
                "AGENTOPS_API_BASE": f"http://127.0.0.1:{fake_upstream.server_port}/api",
                "AGENTOPS_ALLOWED_ORIGINS": proxy_base_url,
                "AGENTOPS_HUMAN_SESSION_HMAC_KEY": hmac_key,
                "NEXT_TELEMETRY_DISABLED": "1",
            })
            proxy_env.pop("AGENTOPS_POSTGRES_DSN", None)
            proxy_env.pop("DATABASE_URL", None)
            proxy_proc = start_process(
                [node_binary, str(NEXT_APP / "node_modules" / "next" / "dist" / "bin" / "next"), "dev", "-p", str(proxy_port)],
                cwd=NEXT_APP,
                env=proxy_env,
            )
            wait_for_proxy_next(
                proxy_base_url,
                proxy_proc,
                sensitive,
                production_fail_closed=True,
            )
            proxy_observations.clear()
            bridge_headers = {
                "Cookie": f"theme=dark; agentops_human_session={cookie_a}",
                "Authorization": "Bearer synthetic-machine-readback",
            }
            catchall_status, catchall_payload, catchall_headers = http_json(
                "GET",
                f"{proxy_base_url}/api/mis/not-migrated-production-probe",
                headers=bridge_headers,
            )
            owned_dashboard_status, owned_dashboard_payload, _ = http_json(
                "GET",
                f"{proxy_base_url}/api/mis/dashboard/metrics",
                headers=bridge_headers,
            )
            upstream_count_before_memory_page = len(proxy_observations)
            production_memory_page_status = http_status(
                f"{proxy_base_url}/workspace/memory",
                headers=bridge_headers,
            )
            upstream_count_after_memory_page = len(proxy_observations)
            production_db_before = {
                "memory": adapter.fetchone(
                    "SELECT review_status,owner_user_id FROM memories WHERE memory_id=?",
                    (MEM_OPERATOR,),
                ),
                "requests": int(adapter.fetchone(
                    "SELECT COUNT(*) AS count FROM human_memory_review_requests WHERE memory_id=?",
                    (MEM_OPERATOR,),
                )["count"]),
                "audits": int(adapter.fetchone(
                    "SELECT COUNT(*) AS count FROM audit_logs WHERE entity_type='memories' AND entity_id=?",
                    (MEM_OPERATOR,),
                )["count"]),
                "events": int(adapter.fetchone(
                    "SELECT COUNT(*) AS count FROM runtime_events",
                )["count"]),
            }
            adapter.commit()
            dedicated_status, dedicated_payload, _ = http_json(
                "GET",
                f"{proxy_base_url}/api/mis/memories?workspace_id={WORKSPACE_ID}",
                headers=bridge_headers,
            )
            production_decision_status, production_decision_payload, _ = http_json(
                "POST",
                f"{proxy_base_url}/api/mis/memories/{MEM_OPERATOR}/approve",
                {"workspace_id": WORKSPACE_ID},
                headers={
                    "Cookie": f"agentops_human_session={cookie_a}",
                    "Idempotency-Key": "production-no-db-memory-decision",
                    "Origin": proxy_base_url,
                },
            )
            production_form_status, production_form_payload, _ = http_json(
                "POST",
                f"{proxy_base_url}/workspace/memory/review",
                raw_body=f"memory_id={MEM_OPERATOR}&decision=approve".encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            upstream_count_before_human = len(proxy_observations)
            direct_human_status, direct_human_payload, _ = http_json(
                "POST",
                f"{proxy_base_url}/api/mis/human-auth/login",
                {"username": "bootstrap-owner", "password": bootstrap_password},
                headers={"Origin": proxy_base_url},
            )
            direct_session_status, direct_session_payload, _ = http_json(
                "GET",
                f"{proxy_base_url}/api/mis/human-auth/session",
                headers={"Cookie": f"agentops_human_session={cookie_a}"},
            )
            upstream_count_after_human = len(proxy_observations)
            production_db_after = {
                "memory": adapter.fetchone(
                    "SELECT review_status,owner_user_id FROM memories WHERE memory_id=?",
                    (MEM_OPERATOR,),
                ),
                "requests": int(adapter.fetchone(
                    "SELECT COUNT(*) AS count FROM human_memory_review_requests WHERE memory_id=?",
                    (MEM_OPERATOR,),
                )["count"]),
                "audits": int(adapter.fetchone(
                    "SELECT COUNT(*) AS count FROM audit_logs WHERE entity_type='memories' AND entity_id=?",
                    (MEM_OPERATOR,),
                )["count"]),
                "events": int(adapter.fetchone(
                    "SELECT COUNT(*) AS count FROM runtime_events",
                )["count"]),
            }
            adapter.commit()
            bridge_evidence = json.dumps({
                "catchall": catchall_payload,
                "dedicated": dedicated_payload,
                "catchall_headers": catchall_headers,
            }, sort_keys=True)
            production_proxy_conditions = {
                "catchall_route_owner_required": (
                    catchall_status == 503
                    and catchall_payload.get("error") == "typescript_route_owner_required"
                    and catchall_payload.get("python_proxy_performed") is False
                ),
                "owned_dashboard_unavailable": (
                    owned_dashboard_status == 503
                    and owned_dashboard_payload.get("error") == "typescript_control_plane_unavailable"
                ),
                "memory_page_renders_without_upstream": (
                    production_memory_page_status == 200
                    and upstream_count_before_memory_page == 0
                    and upstream_count_after_memory_page == upstream_count_before_memory_page
                ),
                "memory_read_unavailable": (
                    dedicated_status == 503
                    and dedicated_payload.get("error") == "typescript_control_plane_unavailable"
                ),
                "memory_decision_unavailable": (
                    production_decision_status == 503
                    and production_decision_payload.get("error") == "typescript_control_plane_unavailable"
                ),
                "memory_form_route_owner_required": (
                    production_form_status == 503
                    and production_form_payload.get("error") == "typescript_route_owner_required"
                    and production_form_payload.get("python_proxy_performed") is False
                ),
                "no_python_upstream_requests": len(proxy_observations) == 0,
                "catchall_does_not_set_human_cookie": (
                    "agentops_human_session=" not in catchall_headers.get("set-cookie", "")
                ),
                "bridge_evidence_omits_human_cookie": cookie_a not in bridge_evidence,
                "human_login_unavailable": (
                    direct_human_status == 503
                    and direct_human_payload.get("error") == "typescript_control_plane_unavailable"
                ),
                "human_session_unavailable": (
                    direct_session_status == 503
                    and direct_session_payload.get("error") == "typescript_control_plane_unavailable"
                ),
                "human_routes_do_not_use_upstream": (
                    upstream_count_before_human == 0
                    and upstream_count_before_human == upstream_count_after_human
                ),
                "database_unchanged": production_db_before == production_db_after,
            }
            production_proxy_diagnostics = {
                "conditions": production_proxy_conditions,
                "statuses": {
                    "catchall": catchall_status,
                    "dashboard": owned_dashboard_status,
                    "memory_page": production_memory_page_status,
                    "memory_read": dedicated_status,
                    "memory_decision": production_decision_status,
                    "memory_form": production_form_status,
                    "human_login": direct_human_status,
                    "human_session": direct_session_status,
                },
                "errors": {
                    "catchall": catchall_payload.get("error"),
                    "dashboard": owned_dashboard_payload.get("error"),
                    "memory_read": dedicated_payload.get("error"),
                    "memory_decision": production_decision_payload.get("error"),
                    "memory_form": production_form_payload.get("error"),
                    "human_login": direct_human_payload.get("error"),
                    "human_session": direct_session_payload.get("error"),
                },
                "upstream_request_counts": {
                    "before_memory_page": upstream_count_before_memory_page,
                    "after_memory_page": upstream_count_after_memory_page,
                    "before_human_routes": upstream_count_before_human,
                    "after_human_routes": upstream_count_after_human,
                    "final": len(proxy_observations),
                },
            }
            check(
                checks,
                failures,
                "production_proxy_memory_routes_fail_closed_without_upstream_or_db_write",
                all(production_proxy_conditions.values()),
            )

            stop_process(proxy_proc)
            proxy_proc = None
            free_proxy_port = free_port()
            free_proxy_base_url = f"http://127.0.0.1:{free_proxy_port}"
            free_proxy_env = os.environ.copy()
            free_proxy_env.update({
                "AGENTOPS_DEPLOYMENT_MODE": "free_local",
                "AGENTOPS_CONTROL_PLANE_MODE": "proxy",
                "AGENTOPS_API_BASE": f"http://127.0.0.1:{fake_upstream.server_port}/api",
                "AGENTOPS_ALLOWED_ORIGINS": free_proxy_base_url,
                "AGENTOPS_HUMAN_SESSION_HMAC_KEY": hmac_key,
                "NEXT_TELEMETRY_DISABLED": "1",
            })
            proxy_proc = start_process(
                [node_binary, str(NEXT_APP / "node_modules" / "next" / "dist" / "bin" / "next"), "dev", "-p", str(free_proxy_port)],
                cwd=NEXT_APP,
                env=free_proxy_env,
            )
            wait_for_proxy_next(free_proxy_base_url, proxy_proc, sensitive)
            proxy_observations.clear()
            free_headers = {
                "Cookie": f"theme=dark; agentops_human_session={cookie_a}",
                "Authorization": "Bearer synthetic-machine-readback",
            }
            free_get_status, free_get_payload, free_get_headers = http_json(
                "GET",
                f"{free_proxy_base_url}/api/mis/memories?workspace_id={WORKSPACE_ID}",
                headers=free_headers,
            )
            free_decision_status, free_decision_payload, free_decision_headers = http_json(
                "POST",
                f"{free_proxy_base_url}/api/mis/memories/{MEM_OPERATOR}/approve",
                {"workspace_id": WORKSPACE_ID},
                headers=free_headers,
            )
            free_evidence = json.dumps({
                "get": free_get_payload,
                "decision": free_decision_payload,
                "get_headers": free_get_headers,
                "decision_headers": free_decision_headers,
            }, sort_keys=True)
            check(
                checks,
                failures,
                "free_local_proxy_compatibility_preserves_machine_auth_and_isolates_human_cookie",
                free_get_status == 200
                and free_decision_status == 200
                and len(proxy_observations) == 2
                and all(item["human_cookie_received"] is False for item in proxy_observations)
                and all(item["compatibility_cookie_received"] is True for item in proxy_observations)
                and all(item["authorization_received"] is True for item in proxy_observations)
                and "agentops_human_session=" not in free_get_headers.get("set-cookie", "")
                and "agentops_human_session=" not in free_decision_headers.get("set-cookie", "")
                and "legacy_pref=ok" in free_get_headers.get("set-cookie", "")
                and "legacy_pref=ok" in free_decision_headers.get("set-cookie", "")
                and cookie_a not in free_evidence,
            )

            output = {
                "ok": not failures,
                "contract": CONTRACT_ID,
                "checks": checks,
                "failures": failures,
                "production_proxy_diagnostics": production_proxy_diagnostics,
                "dynamic_postgres_smoke": True,
                "nextjs_control_plane_started": True,
                "python_api_started": False,
                "python_or_sqlite_commercial_default": False,
                "real_external_side_effects": False,
                "credential_values_omitted": True,
                "raw_private_content_omitted": True,
            }
            print(json.dumps(output, indent=2, sort_keys=True))
            return 0 if not failures else 1
        except Exception as exc:
            print(json.dumps({
                "ok": False,
                "contract": CONTRACT_ID,
                "error": redact(str(exc), sensitive),
                "traceback": redact(traceback.format_exc(), sensitive),
                "python_api_started": False,
                "credential_values_omitted": True,
            }, indent=2, sort_keys=True))
            return 1
        finally:
            if pw_env is not None:
                try:
                    playwright(pw_env, "close", timeout=30)
                except Exception:
                    pass
            for blocker in blockers:
                try:
                    blocker.rollback()
                    blocker.close()
                except Exception:
                    pass
            if adapter is not None:
                try:
                    adapter.close()
                except Exception:
                    pass
            if next_proc is not None:
                stop_process(next_proc)
            if proxy_proc is not None:
                stop_process(proxy_proc)
            if fake_upstream is not None:
                fake_upstream.shutdown()
                fake_upstream.server_close()
            if fake_upstream_thread is not None:
                fake_upstream_thread.join(timeout=5)
            if base_dsn:
                try:
                    cleanup = connect_postgres_when_ready(base_dsn, secret=pg_secret)
                    cleanup.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                    cleanup.commit()
                    cleanup.close()
                except Exception:
                    pass
            if container:
                container_smoke.run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
