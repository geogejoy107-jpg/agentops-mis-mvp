"""Human browser authentication for private AgentOps MIS hosts."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from http.cookies import SimpleCookie


SESSION_COOKIE = "agentops_human_session"
SESSION_TTL_SECONDS = 12 * 60 * 60
ROLE_RANK = {"viewer": 10, "operator": 20, "approver": 30, "owner": 40}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS human_accounts (
    account_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'local-demo',
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('owner','operator','approver','viewer')),
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    password_params_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL CHECK(status IN ('active','disabled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS human_sessions (
    session_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    session_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('active','revoked','expired')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT,
    revoked_at TEXT,
    FOREIGN KEY(account_id) REFERENCES human_accounts(account_id)
);

CREATE INDEX IF NOT EXISTS idx_human_sessions_hash ON human_sessions(session_hash);
CREATE INDEX IF NOT EXISTS idx_human_sessions_account ON human_sessions(account_id,status);
"""


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_reference(session_id: str) -> str:
    digest = hashlib.sha256(f"agentops-human-session-ref-v1:{session_id}".encode("utf-8")).hexdigest()
    return f"hsref_{digest[:16]}"


def init_schema(conn) -> None:
    conn.executescript(SCHEMA_SQL)


def required(env=None) -> bool:
    env = env or os.environ
    configured = str(env.get("AGENTOPS_HUMAN_AUTH_REQUIRED", "")).strip().lower()
    if configured:
        return configured in {"1", "true", "yes", "on"}
    mode = str(env.get("AGENTOPS_DEPLOYMENT_MODE", "local")).strip().lower()
    return mode == "private_host"


def cookie_secure(env=None) -> bool:
    env = env or os.environ
    configured = str(env.get("AGENTOPS_COOKIE_SECURE", "")).strip().lower()
    if configured:
        return configured in {"1", "true", "yes", "on"}
    return required(env)


def allowed_origins(env=None) -> list[str]:
    env = env or os.environ
    return sorted({
        item.strip().rstrip("/")
        for item in str(env.get("AGENTOPS_ALLOWED_ORIGINS", "")).split(",")
        if item.strip()
    })


def origin_error(headers) -> tuple[dict, int] | None:
    allowed = allowed_origins()
    if not allowed:
        return None
    supplied = (headers.get("Origin") or "").strip().rstrip("/")
    if supplied in allowed:
        return None
    return {
        "error": "origin_validation_failed",
        "message": "The browser Origin is not allowed for this Host.",
        "origin_omitted": True,
    }, 403


def account_public(row) -> dict:
    return {
        "account_id": row["account_id"],
        "workspace_id": row["workspace_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "status": row["status"] if "status" in row.keys() else row["account_status"],
    }


def password_hash(password: str, salt: bytes, params=None) -> tuple[str, dict]:
    params = params or {"name": "scrypt", "n": 16384, "r": 8, "p": 1, "dklen": 32}
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=int(params["n"]),
        r=int(params["r"]),
        p=int(params["p"]),
        dklen=int(params["dklen"]),
    )
    return derived.hex(), params


def password_valid(password: str, row) -> bool:
    try:
        params = json.loads(row["password_params_json"] or "{}")
        actual, _ = password_hash(password, bytes.fromhex(row["password_salt"]), params)
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return False
    return hmac.compare_digest(actual, row["password_hash"])


def session_token(headers) -> str:
    raw = (headers.get("Cookie") if headers else "") or ""
    if not raw:
        return ""
    cookie = SimpleCookie()
    try:
        cookie.load(raw)
    except Exception:
        return ""
    morsel = cookie.get(SESSION_COOKIE)
    return morsel.value.strip() if morsel else ""


def csrf_token(token: str) -> str:
    return hmac.new(token.encode("utf-8"), b"agentops-human-csrf-v1", hashlib.sha256).hexdigest()


def auth_context(conn, headers, *, touch=True) -> tuple[dict | None, dict | None]:
    token = session_token(headers)
    if not token:
        return None, {"error": "human_auth_required", "message": "A human browser session is required."}
    row = conn.execute(
        """
        SELECT s.*,a.workspace_id,a.username,a.display_name,a.role,a.status AS account_status
        FROM human_sessions s
        JOIN human_accounts a ON a.account_id=s.account_id
        WHERE s.session_hash=?
        """,
        (token_hash(token),),
    ).fetchone()
    if not row or row["status"] != "active" or row["account_status"] != "active":
        return None, {"error": "human_session_invalid", "message": "The human browser session is invalid or revoked."}
    if row["expires_at"] <= now_iso():
        conn.execute("UPDATE human_sessions SET status='expired',revoked_at=? WHERE session_id=?", (now_iso(), row["session_id"]))
        return None, {"error": "human_session_expired", "message": "The human browser session has expired."}
    if touch:
        conn.execute("UPDATE human_sessions SET last_seen_at=? WHERE session_id=?", (now_iso(), row["session_id"]))
    return {
        "mode": "human_session",
        "session_id": row["session_id"],
        "account_id": row["account_id"],
        "workspace_id": row["workspace_id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "session_token": token,
        "expires_at": row["expires_at"],
    }, None


def required_role(path: str, method: str) -> str:
    if method == "GET":
        if path in {
            "/api/human-auth/sessions",
            "/api/workers/local/logs",
            "/api/runs/export",
            "/api/memories/export",
        }:
            return "owner"
        return "viewer"
    if path == "/api/knowledge/index" or path.startswith((
        "/api/human-auth/sessions",
        "/api/workers/local/",
        "/api/integrations/",
        "/api/migration/",
        "/api/commander/work-packages/",
    )):
        return "owner"
    if path.startswith(("/api/approvals/", "/api/memories/", "/api/agent-plans/")):
        return "approver"
    return "operator"


def request_auth(conn, headers, path: str, method: str) -> tuple[dict | None, tuple[dict, int] | None]:
    context, error = auth_context(conn, headers)
    if error:
        return None, (error, 401)
    role = required_role(path, method)
    if ROLE_RANK.get(context["role"], 0) < ROLE_RANK[role]:
        return None, ({
            "error": "human_role_forbidden",
            "message": f"This action requires the {role} role.",
            "required_role": role,
            "current_role": context["role"],
        }, 403)
    if method in {"POST", "PATCH", "PUT", "DELETE"}:
        invalid_origin = origin_error(headers)
        if invalid_origin:
            return None, invalid_origin
        supplied = (headers.get("X-AgentOps-CSRF") or "").strip()
        expected = csrf_token(context["session_token"])
        if not supplied or not hmac.compare_digest(supplied, expected):
            return None, ({
                "error": "csrf_validation_failed",
                "message": "A valid X-AgentOps-CSRF token is required for state-changing browser requests.",
            }, 403)
    return context, None


def status(conn, headers) -> dict:
    is_required = required()
    account_count = int(conn.execute("SELECT COUNT(*) FROM human_accounts WHERE status='active'").fetchone()[0])
    context, _error = auth_context(conn, headers) if is_required else (None, None)
    payload = {
        "provider": "agentops-human-auth",
        "required": is_required,
        "authenticated": bool(context),
        "bootstrap_required": is_required and account_count == 0,
        "bootstrap_available": bool(os.environ.get("AGENTOPS_OWNER_SETUP_CODE", "").strip()),
        "cookie_secure": cookie_secure(),
        "token_omitted": True,
    }
    if context:
        payload.update({
            "user": {key: context[key] for key in ("account_id", "workspace_id", "username", "display_name", "role")},
            "csrf_token": csrf_token(context["session_token"]),
            "session_expires_at": context["expires_at"],
        })
    return payload


def session_cookie(token: str, *, clear=False) -> str:
    parts = [f"{SESSION_COOKIE}={'' if clear else token}", "Path=/", "HttpOnly", "SameSite=Strict"]
    if clear:
        parts.extend(["Max-Age=0", "Expires=Thu, 01 Jan 1970 00:00:00 GMT"])
    else:
        parts.append(f"Max-Age={SESSION_TTL_SECONDS}")
    if cookie_secure():
        parts.append("Secure")
    return "; ".join(parts)


def create_session(conn, account_row) -> tuple[dict, str, dict]:
    token = secrets.token_urlsafe(32)
    created_at = now_iso()
    expires_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=SESSION_TTL_SECONDS)).isoformat()
    session_id = new_id("hsess")
    conn.execute(
        "INSERT INTO human_sessions(session_id,account_id,session_hash,status,created_at,expires_at,last_seen_at,revoked_at) VALUES(?,?,?,?,?,?,?,?)",
        (session_id, account_row["account_id"], token_hash(token), "active", created_at, expires_at, created_at, None),
    )
    conn.execute("UPDATE human_accounts SET last_login_at=?,updated_at=? WHERE account_id=?", (created_at, created_at, account_row["account_id"]))
    return {
        "provider": "agentops-human-auth",
        "authenticated": True,
        "user": account_public(account_row),
        "csrf_token": csrf_token(token),
        "session_expires_at": expires_at,
        "token_omitted": True,
    }, token, {"account_id": account_row["account_id"], "session_id": session_id}


def bootstrap_owner(conn, body) -> tuple[dict, int, str | None, dict]:
    if not required():
        return {"error": "human_auth_disabled", "message": "Human authentication is not enabled."}, 409, None, {"event": "bootstrap_blocked"}
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    if conn.execute("SELECT 1 FROM human_accounts LIMIT 1").fetchone():
        return {"error": "owner_already_initialized", "message": "The owner account is already initialized."}, 409, None, {"event": "bootstrap_blocked"}
    expected = os.environ.get("AGENTOPS_OWNER_SETUP_CODE", "").strip()
    supplied = str(body.get("setup_code") or "").strip()
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        return {"error": "invalid_setup_code", "message": "The one-time owner setup code is invalid or unavailable."}, 401, None, {"event": "bootstrap_failed"}
    username = str(body.get("username") or "").strip().lower()
    password = str(body.get("password") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", username):
        return {"error": "invalid_username", "message": "Username must be 3-64 lowercase letters, digits, dot, underscore, or dash."}, 400, None, {"event": "bootstrap_failed"}
    if len(password) < 12:
        return {"error": "weak_password", "message": "Password must contain at least 12 characters."}, 400, None, {"event": "bootstrap_failed"}
    salt = secrets.token_bytes(16)
    derived, params = password_hash(password, salt)
    account_id = new_id("husr")
    created_at = now_iso()
    display_name = str(body.get("display_name") or username).strip()[:80] or username
    conn.execute(
        "INSERT INTO human_accounts(account_id,workspace_id,username,display_name,role,password_hash,password_salt,password_params_json,status,created_at,updated_at,last_login_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (account_id, "local-demo", username, display_name, "owner", derived, salt.hex(), json.dumps(params, sort_keys=True), "active", created_at, created_at, None),
    )
    account = conn.execute("SELECT * FROM human_accounts WHERE account_id=?", (account_id,)).fetchone()
    payload, token, audit = create_session(conn, account)
    return payload, 201, token, {"event": "owner_bootstrapped", **audit}


def login(conn, body) -> tuple[dict, int, str | None, dict]:
    username = str(body.get("username") or "").strip().lower()
    password = str(body.get("password") or "")
    account = conn.execute("SELECT * FROM human_accounts WHERE username=?", (username,)).fetchone()
    username_hash = hashlib.sha256(username.encode("utf-8")).hexdigest()
    if not account or account["status"] != "active" or not password_valid(password, account):
        return {"error": "invalid_credentials", "message": "Username or password is invalid."}, 401, None, {"event": "login_failed", "username_hash": username_hash}
    payload, token, audit = create_session(conn, account)
    return payload, 200, token, {"event": "login_succeeded", **audit}


def logout(conn, headers) -> tuple[dict, int, dict]:
    invalid_origin = origin_error(headers)
    if invalid_origin:
        payload, status = invalid_origin
        return payload, status, {"event": "logout_failed"}
    context, error = auth_context(conn, headers, touch=False)
    if error:
        return error, 401, {"event": "logout_failed"}
    supplied = (headers.get("X-AgentOps-CSRF") or "").strip()
    if not supplied or not hmac.compare_digest(supplied, csrf_token(context["session_token"])):
        return {"error": "csrf_validation_failed", "message": "A valid X-AgentOps-CSRF token is required."}, 403, {"event": "logout_failed", "account_id": context["account_id"]}
    timestamp = now_iso()
    conn.execute("UPDATE human_sessions SET status='revoked',revoked_at=? WHERE session_id=?", (timestamp, context["session_id"]))
    return {"provider": "agentops-human-auth", "authenticated": False, "token_omitted": True}, 200, {
        "event": "logout",
        "account_id": context["account_id"],
        "session_id": context["session_id"],
    }


def _expire_account_sessions(conn, account_id: str) -> int:
    timestamp = now_iso()
    cursor = conn.execute(
        """
        UPDATE human_sessions
        SET status='expired',revoked_at=?
        WHERE account_id=? AND status='active' AND expires_at<=?
        """,
        (timestamp, account_id, timestamp),
    )
    return max(0, int(cursor.rowcount or 0))


def list_sessions(conn, context) -> tuple[dict, int]:
    if not context:
        return {"error": "human_auth_required", "message": "A human browser session is required."}, 401
    _expire_account_sessions(conn, context["account_id"])
    rows = conn.execute(
        """
        SELECT session_id,status,created_at,expires_at,last_seen_at,revoked_at
        FROM human_sessions
        WHERE account_id=?
        ORDER BY created_at DESC
        LIMIT 50
        """,
        (context["account_id"],),
    ).fetchall()
    sessions = [
        {
            "session_ref": session_reference(row["session_id"]),
            "status": row["status"],
            "current": hmac.compare_digest(row["session_id"], context["session_id"]),
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
            "last_seen_at": row["last_seen_at"],
            "revoked_at": row["revoked_at"],
        }
        for row in rows
    ]
    return {
        "provider": "agentops-human-auth",
        "operation": "human_sessions_list",
        "sessions": sessions,
        "current_session_ref": session_reference(context["session_id"]),
        "active_count": sum(1 for row in sessions if row["status"] == "active"),
        "session_count": len(sessions),
        "session_id_omitted": True,
        "session_hash_omitted": True,
        "token_omitted": True,
    }, 200


def revoke_sessions(conn, context, body) -> tuple[dict, int, dict]:
    if not context:
        payload = {"error": "human_auth_required", "message": "A human browser session is required."}
        return payload, 401, {"event": "sessions_revoke_failed", "target_ref": "unavailable"}
    body = body if isinstance(body, dict) else {}
    unexpected = sorted(set(body) - {"session_ref", "all_other"})
    requested_ref = str(body.get("session_ref") or "").strip()
    all_other = body.get("all_other") is True
    has_session_ref = "session_ref" in body
    has_all_other = "all_other" in body
    invalid_operation = (
        has_session_ref == has_all_other
        or (has_session_ref and not requested_ref)
        or (has_all_other and not all_other)
    )
    if unexpected or invalid_operation:
        payload = {
            "error": "invalid_session_revoke_request",
            "message": "Provide exactly one of session_ref or all_other=true.",
            "unexpected_fields": unexpected,
        }
        return payload, 400, {"event": "sessions_revoke_failed", "target_ref": requested_ref or "all_other"}

    _expire_account_sessions(conn, context["account_id"])
    current_ref = session_reference(context["session_id"])
    timestamp = now_iso()
    revoked_refs: list[str] = []

    if all_other:
        rows = conn.execute(
            """
            SELECT session_id FROM human_sessions
            WHERE account_id=? AND status='active' AND session_id<>?
            """,
            (context["account_id"], context["session_id"]),
        ).fetchall()
        revoked_refs = [session_reference(row["session_id"]) for row in rows]
        if rows:
            conn.execute(
                """
                UPDATE human_sessions
                SET status='revoked',revoked_at=?
                WHERE account_id=? AND status='active' AND session_id<>?
                """,
                (timestamp, context["account_id"], context["session_id"]),
            )
        target_ref = "all_other"
    else:
        target = None
        rows = conn.execute(
            """
            SELECT session_id,status FROM human_sessions
            WHERE account_id=?
            """,
            (context["account_id"],),
        ).fetchall()
        for row in rows:
            if hmac.compare_digest(session_reference(row["session_id"]), requested_ref):
                target = row
                break
        if target is None:
            payload = {"error": "human_session_not_found", "message": "The browser session was not found."}
            return payload, 404, {"event": "sessions_revoke_failed", "target_ref": requested_ref}
        if hmac.compare_digest(target["session_id"], context["session_id"]):
            payload = {
                "error": "current_session_requires_logout",
                "message": "Use sign out to revoke the current browser session.",
                "current_session_ref": current_ref,
            }
            return payload, 409, {"event": "sessions_revoke_blocked", "target_ref": requested_ref}
        target_ref = requested_ref
        if target["status"] == "active":
            conn.execute(
                """
                UPDATE human_sessions
                SET status='revoked',revoked_at=?
                WHERE account_id=? AND session_id=? AND status='active'
                """,
                (timestamp, context["account_id"], target["session_id"]),
            )
            revoked_refs = [requested_ref]

    return {
        "provider": "agentops-human-auth",
        "operation": "human_sessions_revoke",
        "status": "revoked" if revoked_refs else "no_active_session_changed",
        "revoked_count": len(revoked_refs),
        "revoked_session_refs": revoked_refs,
        "current_session_ref": current_ref,
        "current_session_preserved": True,
        "session_id_omitted": True,
        "session_hash_omitted": True,
        "token_omitted": True,
    }, 200, {
        "event": "sessions_revoked",
        "target_ref": target_ref,
        "revoked_session_refs": revoked_refs,
    }
