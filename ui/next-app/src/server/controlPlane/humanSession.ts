import {
  createHash,
  createHmac,
  randomBytes,
  scrypt as scryptCallback,
  timingSafeEqual,
} from "node:crypto";
import type { PoolClient } from "pg";

import { withPostgresTransaction } from "./db";
import {
  HUMAN_PASSWORD_MAX_LENGTH,
  HUMAN_PASSWORD_MIN_LENGTH,
  HUMAN_SCRYPT_PARAMS,
} from "./humanPasswordPolicy";
import { ControlPlaneHttpError } from "./http";
import { appendAudit, newLedgerId } from "./ledger";
import {
  assertHumanMemorySchemaReady,
  SchemaReadinessError,
} from "./schemaReadiness";

const SESSION_COOKIE = "agentops_human_session";
const LOGIN_WINDOW_MS = 5 * 60 * 1000;
const LOGIN_BLOCK_MS = 5 * 60 * 1000;
const LOGIN_MAX_FAILURES = 8;
const LOGIN_THROTTLE_RETENTION_MS = 24 * 60 * 60 * 1000;
const LOGIN_THROTTLE_CLEANUP_BATCH = 128;
const MACHINE_CREDENTIAL_HEADERS = [
  "authorization",
  "x-agentops-admin-key",
  "x-agentops-workspace-admin-key",
  "x-agentops-api-key",
  "x-api-key",
];
const REVIEW_ROLES = new Set(["owner", "approver"]);
const DUMMY_SCRYPT_SALT = Buffer.from("9d75d03f6ac94ea71c1aa0357bcf1a6d", "hex");
const DUMMY_SCRYPT_HASH = Buffer.from("2db67be954501721e3cc1358f2f28be1493d502655667096e80a2e9e87fb09f4", "hex");
let scryptWorkCount = 0;

declare global {
  var __agentOpsHumanLoginInFlight: number | undefined;
}

type HumanSessionRow = {
  session_id: string;
  user_id: string;
  session_hash: string;
  status: string;
  created_at: string;
  expires_at: string;
  last_seen_at: string | null;
  revoked_at: string | null;
};

type UserRow = {
  user_id: string;
  name: string;
};

export type HumanLoginCredentialForVerification = UserRow & {
  credential_id: string;
  username: string;
  password_hash: string;
  password_salt: string;
  password_params_json: string;
  credential_status: string;
};

type CredentialRow = HumanLoginCredentialForVerification;

type MembershipRow = {
  workspace_id: string;
  user_id: string;
  role: string;
  status: string;
};

type ThrottleRow = {
  bucket_key: string;
  failure_count: number;
  window_started_at: string;
  blocked_until: string | null;
};

export type HumanSessionIdentity = {
  mode: "human_session";
  sessionId: string;
  sessionRef: string;
  userId: string;
  userName: string;
  workspaceId: string;
  membershipRole: string;
};

async function assertHumanRuntimeSchemaReady(client: PoolClient) {
  try {
    await assertHumanMemorySchemaReady(client);
  } catch (error) {
    if (error instanceof SchemaReadinessError) {
      throw new ControlPlaneHttpError(
        503,
        error.code,
        "The Human Session database schema is not ready for commercial runtime traffic.",
      );
    }
    throw error;
  }
}

function hmacKey() {
  const key = String(process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY || "");
  if (Buffer.byteLength(key, "utf8") < 32) {
    throw new ControlPlaneHttpError(
      503,
      "human_session_config_required",
      "AGENTOPS_HUMAN_SESSION_HMAC_KEY must contain at least 32 bytes.",
    );
  }
  return key;
}

function hmac(label: string, value: string) {
  return createHmac("sha256", hmacKey()).update(`${label}:${value}`, "utf8").digest("hex");
}

function sameValue(left: string, right: string) {
  const leftHash = createHash("sha256").update(left, "utf8").digest();
  const rightHash = createHash("sha256").update(right, "utf8").digest();
  return timingSafeEqual(leftHash, rightHash);
}

function sessionHash(token: string) {
  return hmac("session", token);
}

function csrfToken(token: string) {
  return hmac("csrf", token);
}

export function opaqueReference(label: string, value: string) {
  return `${label}_${hmac(label, value).slice(0, 16)}`;
}

function normalizedUsername(value: unknown) {
  const username = String(value ?? "").trim().toLowerCase();
  return /^[a-z0-9][a-z0-9._-]{2,63}$/.test(username) ? username : "";
}

function sessionTtlSeconds() {
  const configured = Number(process.env.AGENTOPS_HUMAN_SESSION_TTL_SECONDS || 12 * 60 * 60);
  if (!Number.isFinite(configured)) return 12 * 60 * 60;
  return Math.max(5 * 60, Math.min(Math.trunc(configured), 24 * 60 * 60));
}

function configuredOrigins() {
  const raw = String(process.env.AGENTOPS_ALLOWED_ORIGINS || "");
  const origins = raw.split(",").map((item) => item.trim()).filter(Boolean);
  if (!origins.length) {
    throw new ControlPlaneHttpError(
      503,
      "origin_configuration_required",
      "AGENTOPS_ALLOWED_ORIGINS is required for Human Session routes.",
    );
  }
  const normalized = new Map<string, URL>();
  for (const item of origins) {
    let parsed: URL;
    try {
      parsed = new URL(item);
    } catch {
      throw new ControlPlaneHttpError(503, "origin_configuration_invalid", "AGENTOPS_ALLOWED_ORIGINS contains an invalid origin.");
    }
    const isLoopback = parsed.hostname === "localhost"
      || parsed.hostname === "127.0.0.1"
      || parsed.hostname === "[::1]"
      || parsed.hostname === "::1";
    if ((parsed.protocol !== "https:" && !(parsed.protocol === "http:" && isLoopback))
      || parsed.username
      || parsed.password
      || (parsed.pathname !== "/" && parsed.pathname !== "")
      || parsed.search
      || parsed.hash) {
      throw new ControlPlaneHttpError(
        503,
        "origin_configuration_invalid",
        "Human Session origins must be HTTPS origins or loopback HTTP origins without paths or credentials.",
      );
    }
    normalized.set(parsed.origin, parsed);
  }
  return normalized;
}

export function rejectMachineCredentials(headers: Headers) {
  if (MACHINE_CREDENTIAL_HEADERS.some((name) => Boolean(String(headers.get(name) || "").trim()))) {
    throw new ControlPlaneHttpError(
      401,
      "machine_credential_not_allowed",
      "Agent Gateway and workspace administration credentials cannot authorize a Human Session action.",
    );
  }
}

export function validateWriteOrigin(headers: Headers) {
  const origins = configuredOrigins();
  const supplied = String(headers.get("origin") || "").trim();
  const host = String(headers.get("host") || "").trim().toLowerCase();
  const parsed = origins.get(supplied);
  if (!parsed || !host || parsed.host.toLowerCase() !== host) {
    throw new ControlPlaneHttpError(
      403,
      "origin_validation_failed",
      "The browser Origin and direct Host are not allowed.",
    );
  }
  return parsed;
}

function cookieValues(headers: Headers, name: string) {
  const raw = String(headers.get("cookie") || "");
  return raw.split(";").map((item) => item.trim()).filter((item) => item.startsWith(`${name}=`)).map((item) => {
    const value = item.slice(name.length + 1);
    try {
      return decodeURIComponent(value);
    } catch {
      return "";
    }
  });
}

function suppliedSessionToken(headers: Headers) {
  const values = cookieValues(headers, SESSION_COOKIE);
  if (values.length !== 1 || !/^[A-Za-z0-9_-]{32,256}$/.test(values[0])) return "";
  return values[0];
}

function cookie(token: string, origin: URL, clear = false) {
  const parts = [
    `${SESSION_COOKIE}=${clear ? "" : encodeURIComponent(token)}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Strict",
  ];
  if (origin.protocol === "https:") parts.push("Secure");
  if (clear) {
    parts.push("Max-Age=0", "Expires=Thu, 01 Jan 1970 00:00:00 GMT");
  } else {
    parts.push(`Max-Age=${sessionTtlSeconds()}`);
  }
  return parts.join("; ");
}

function publicUser(row: UserRow) {
  return { user_id: row.user_id, name: row.name };
}

function parsePasswordParams(raw: string) {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new ControlPlaneHttpError(503, "human_credential_state_invalid", "Human credential state is invalid.");
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new ControlPlaneHttpError(503, "human_credential_state_invalid", "Human credential state is invalid.");
  }
  const value = parsed as Record<string, unknown>;
  const n = Number(value.n);
  const r = Number(value.r);
  const p = Number(value.p);
  const keylen = Number(value.keylen);
  if (value.name !== HUMAN_SCRYPT_PARAMS.name
    || ![n, r, p, keylen].every(Number.isInteger)
    || n !== HUMAN_SCRYPT_PARAMS.n
    || r !== HUMAN_SCRYPT_PARAMS.r
    || p !== HUMAN_SCRYPT_PARAMS.p
    || keylen !== HUMAN_SCRYPT_PARAMS.keylen) {
    throw new ControlPlaneHttpError(503, "human_credential_state_invalid", "Human credential parameters are invalid.");
  }
  return { n, r, p, keylen };
}

function deriveScrypt(password: string, salt: Buffer, params: { n: number; r: number; p: number; keylen: number }) {
  return new Promise<Buffer>((resolve, reject) => {
    scryptCallback(password, salt, params.keylen, {
      N: params.n,
      r: params.r,
      p: params.p,
      maxmem: 128 * 1024 * 1024,
    }, (error, derived) => {
      if (error) reject(error);
      else {
        scryptWorkCount += 1;
        resolve(derived as Buffer);
      }
    });
  });
}

async function passwordMatches(password: string, credential: CredentialRow) {
  const params = parsePasswordParams(credential.password_params_json);
  const validSalt = /^[a-f0-9]{32,128}$/i.test(credential.password_salt);
  const validHash = /^[a-f0-9]{64}$/i.test(credential.password_hash);
  const salt = validSalt
    ? Buffer.from(credential.password_salt, "hex")
    : Buffer.from(hmac("invalid-credential-salt", credential.credential_id).slice(0, 32), "hex");
  const derived = await deriveScrypt(password, salt, params);
  if (!validSalt || !validHash) return false;
  return timingSafeEqual(derived, Buffer.from(credential.password_hash, "hex"));
}

export async function verifyHumanLoginPassword(
  password: string,
  credential: CredentialRow | undefined,
) {
  const validShape = password.length >= HUMAN_PASSWORD_MIN_LENGTH && password.length <= HUMAN_PASSWORD_MAX_LENGTH;
  if (credential?.credential_status === "active") {
    const matches = await passwordMatches(validShape ? password : "invalid-login-password", credential);
    return validShape && matches;
  }
  const derived = await deriveScrypt(validShape ? password : "invalid-login-password", DUMMY_SCRYPT_SALT, {
    n: HUMAN_SCRYPT_PARAMS.n,
    r: HUMAN_SCRYPT_PARAMS.r,
    p: HUMAN_SCRYPT_PARAMS.p,
    keylen: HUMAN_SCRYPT_PARAMS.keylen,
  });
  timingSafeEqual(derived, DUMMY_SCRYPT_HASH);
  return false;
}

export function resetHumanScryptWorkCountForTests() {
  scryptWorkCount = 0;
}

export function humanScryptWorkCountForTests() {
  return scryptWorkCount;
}

function throttleActive(row: ThrottleRow | undefined, now: Date) {
  return Boolean(row?.blocked_until && Date.parse(row.blocked_until) > now.getTime());
}

function loginAdmissionLimit() {
  const configured = Number(process.env.AGENTOPS_HUMAN_LOGIN_CONCURRENCY || 4);
  if (!Number.isFinite(configured)) return 4;
  return Math.max(1, Math.min(Math.trunc(configured), 16));
}

function acquireLoginAdmission() {
  const inFlight = globalThis.__agentOpsHumanLoginInFlight || 0;
  if (inFlight >= loginAdmissionLimit()) {
    throw new ControlPlaneHttpError(
      429,
      "human_login_capacity_exceeded",
      "Human sign-in capacity is temporarily saturated.",
    );
  }
  globalThis.__agentOpsHumanLoginInFlight = inFlight + 1;
  let released = false;
  return () => {
    if (released) return;
    released = true;
    globalThis.__agentOpsHumanLoginInFlight = Math.max(
      0,
      (globalThis.__agentOpsHumanLoginInFlight || 1) - 1,
    );
  };
}

async function cleanupStaleLoginThrottle(client: PoolClient, now: Date) {
  const staleBefore = new Date(now.getTime() - LOGIN_THROTTLE_RETENTION_MS).toISOString();
  await client.query(
    `DELETE FROM human_login_throttle WHERE bucket_key IN (
      SELECT bucket_key FROM human_login_throttle
      WHERE updated_at < $1 AND (blocked_until IS NULL OR blocked_until < $2)
      ORDER BY updated_at LIMIT $3 FOR UPDATE SKIP LOCKED
    )`,
    [staleBefore, now.toISOString(), LOGIN_THROTTLE_CLEANUP_BATCH],
  );
}

async function recordLoginFailure(client: PoolClient, bucketKey: string, row: ThrottleRow | undefined, now: Date) {
  const windowStarted = row ? Date.parse(row.window_started_at) : Number.NaN;
  const withinWindow = Number.isFinite(windowStarted) && now.getTime() - windowStarted < LOGIN_WINDOW_MS;
  const count = withinWindow ? Number(row?.failure_count || 0) + 1 : 1;
  const startedAt = withinWindow ? row!.window_started_at : now.toISOString();
  const blockedUntil = count >= LOGIN_MAX_FAILURES
    ? new Date(now.getTime() + LOGIN_BLOCK_MS).toISOString()
    : null;
  await client.query(
    `INSERT INTO human_login_throttle(bucket_key,failure_count,window_started_at,blocked_until,updated_at)
    VALUES($1,$2,$3,$4,$5)
    ON CONFLICT (bucket_key) DO UPDATE SET failure_count=EXCLUDED.failure_count,
      window_started_at=EXCLUDED.window_started_at,blocked_until=EXCLUDED.blocked_until,updated_at=EXCLUDED.updated_at`,
    [bucketKey, count, startedAt, blockedUntil, now.toISOString()],
  );
}

export async function establishHumanSession(headers: Headers, body: Record<string, unknown>) {
  rejectMachineCredentials(headers);
  const origin = validateWriteOrigin(headers);
  const username = normalizedUsername(body.username);
  const password = typeof body.password === "string" ? body.password : "";
  const bucketKey = hmac("login-subject", username || "invalid");
  const releaseAdmission = acquireLoginAdmission();
  try {
    return await withPostgresTransaction(async (client) => {
      await assertHumanRuntimeSchemaReady(client);
      const now = new Date();
      await cleanupStaleLoginThrottle(client, now);
      await client.query("SELECT pg_advisory_xact_lock(hashtext($1))", [`agentops-human-login:${bucketKey}`]);
    const throttleResult = await client.query<ThrottleRow>(
      "SELECT bucket_key,failure_count,window_started_at,blocked_until FROM human_login_throttle WHERE bucket_key=$1 FOR UPDATE",
      [bucketKey],
    );
    const throttle = throttleResult.rows[0];
    if (throttleActive(throttle, now)) {
      throw new ControlPlaneHttpError(429, "human_login_throttled", "Sign-in is temporarily blocked after repeated failures.");
    }
    const credentialResult = username
      ? await client.query<CredentialRow>(
          `SELECT credential.credential_id,credential.user_id,credential.username,credential.password_hash,
          credential.password_salt,credential.password_params_json,credential.status AS credential_status,
          users.name
          FROM human_login_credentials credential
          JOIN users ON users.user_id=credential.user_id
          WHERE credential.username=$1 FOR UPDATE OF credential`,
          [username],
        )
      : { rows: [] as CredentialRow[] };
    const credential = credentialResult.rows[0];
    const matches = await verifyHumanLoginPassword(password, credential);
    const activeMemberships = matches
      ? await client.query<MembershipRow>(
          `SELECT workspace_id,user_id,role,status FROM workspace_memberships
          WHERE user_id=$1 AND status='active' ORDER BY workspace_id FOR UPDATE`,
          [credential.user_id],
        )
      : { rows: [] as MembershipRow[] };
    if (!matches || !activeMemberships.rows.length) {
      await recordLoginFailure(client, bucketKey, throttle, now);
      throw new ControlPlaneHttpError(401, "invalid_credentials", "Username or password is invalid.", true);
    }

    await client.query("DELETE FROM human_login_throttle WHERE bucket_key=$1", [bucketKey]);
    const token = randomBytes(32).toString("base64url");
    const sessionId = newLedgerId("hsess");
    const expiresAt = new Date(now.getTime() + sessionTtlSeconds() * 1000).toISOString();
    await client.query(
      `INSERT INTO human_sessions(session_id,user_id,session_hash,status,created_at,expires_at,last_seen_at,revoked_at)
      VALUES($1,$2,$3,'active',$4,$5,$4,NULL)`,
      [sessionId, credential.user_id, sessionHash(token), now.toISOString(), expiresAt],
    );
    await client.query(
      "UPDATE human_login_credentials SET last_login_at=$1,updated_at=$1 WHERE credential_id=$2",
      [now.toISOString(), credential.credential_id],
    );
    const sessionRef = opaqueReference("hsref", sessionId);
    await appendAudit(client, {
      actorType: "user",
      actorId: credential.user_id,
      action: "human_auth.login",
      entityType: "human_sessions",
      entityId: sessionRef,
      after: { status: "active", expires_at: expiresAt },
      metadata: { credentials_omitted: true, session_id_omitted: true, token_omitted: true },
    });
    return {
      status: 200,
      body: {
        ok: true,
        provider: "agentops-human-session",
        authenticated: true,
        user: publicUser(credential),
        memberships: activeMemberships.rows.map((item) => ({ workspace_id: item.workspace_id, role: item.role })),
        csrf_token: csrfToken(token),
        session_expires_at: expiresAt,
        token_omitted: true,
      },
      setCookie: cookie(token, origin),
    };
    });
  } finally {
    releaseAdmission();
  }
}

async function lockSession(client: PoolClient, headers: Headers) {
  rejectMachineCredentials(headers);
  const token = suppliedSessionToken(headers);
  if (!token) {
    throw new ControlPlaneHttpError(401, "human_auth_required", "A Human Session cookie is required.");
  }
  const candidate = await client.query<Pick<HumanSessionRow, "session_id">>(
    "SELECT session_id FROM human_sessions WHERE session_hash=$1",
    [sessionHash(token)],
  );
  const sessionId = candidate.rows[0]?.session_id;
  if (!sessionId) {
    throw new ControlPlaneHttpError(401, "human_session_invalid", "The Human Session is invalid or revoked.");
  }
  const result = await client.query<HumanSessionRow & UserRow>(
    `SELECT session.*,users.name
    FROM human_sessions session
    JOIN users ON users.user_id=session.user_id
    WHERE session.session_id=$1 AND session.session_hash=$2
    FOR UPDATE OF session`,
    [sessionId, sessionHash(token)],
  );
  const row = result.rows[0];
  if (!row || row.status !== "active") {
    throw new ControlPlaneHttpError(401, "human_session_invalid", "The Human Session is invalid or revoked.");
  }
  if (Date.parse(row.expires_at) <= Date.now()) {
    const now = new Date().toISOString();
    await client.query(
      "UPDATE human_sessions SET status='expired',revoked_at=$1 WHERE session_id=$2 AND status='active'",
      [now, row.session_id],
    );
    throw new ControlPlaneHttpError(401, "human_session_expired", "The Human Session has expired.", true);
  }
  return { row, token };
}

export async function authenticateHumanReviewer(
  client: PoolClient,
  headers: Headers,
  requestedWorkspaceId: unknown,
): Promise<HumanSessionIdentity> {
  await assertHumanRuntimeSchemaReady(client);
  return authenticateWorkspaceMembership(client, headers, requestedWorkspaceId, true);
}

export async function authenticateHumanMember(
  client: PoolClient,
  headers: Headers,
  requestedWorkspaceId: unknown,
): Promise<HumanSessionIdentity> {
  await assertHumanRuntimeSchemaReady(client);
  return authenticateWorkspaceMembership(client, headers, requestedWorkspaceId, false);
}

async function authenticateWorkspaceMembership(
  client: PoolClient,
  headers: Headers,
  requestedWorkspaceId: unknown,
  requireReviewAuthority: boolean,
): Promise<HumanSessionIdentity> {
  const { row, token } = await lockSession(client, headers);
  const workspaceId = String(requestedWorkspaceId ?? "").trim();
  if (!/^[A-Za-z0-9._:-]{1,128}$/.test(workspaceId)) {
    throw new ControlPlaneHttpError(403, "workspace_id_required", "A valid workspace id is required.");
  }
  const headerWorkspace = String(headers.get("x-agentops-workspace-id") || "").trim();
  if (headerWorkspace && headerWorkspace !== workspaceId) {
    throw new ControlPlaneHttpError(403, "forbidden", "The request workspace binding does not match.");
  }
  const membershipResult = await client.query<MembershipRow>(
    `SELECT workspace_id,user_id,role,status FROM workspace_memberships
    WHERE workspace_id=$1 AND user_id=$2 FOR UPDATE`,
    [workspaceId, row.user_id],
  );
  const membership = membershipResult.rows[0];
  if (!membership || membership.status !== "active") {
    throw new ControlPlaneHttpError(403, "human_membership_forbidden", "The Human Session is not a member of this workspace.");
  }
  if (requireReviewAuthority && !REVIEW_ROLES.has(membership.role)) {
    throw new ControlPlaneHttpError(403, "human_role_forbidden", "Memory review requires the workspace approver role.");
  }
  if (requireReviewAuthority) {
    validateWriteOrigin(headers);
    const suppliedCsrf = String(headers.get("x-agentops-csrf") || "").trim();
    if (!suppliedCsrf || !sameValue(suppliedCsrf, csrfToken(token))) {
      throw new ControlPlaneHttpError(403, "csrf_validation_failed", "A valid Human Session CSRF token is required.");
    }
  }
  await client.query("UPDATE human_sessions SET last_seen_at=$1 WHERE session_id=$2", [new Date().toISOString(), row.session_id]);
  return {
    mode: "human_session",
    sessionId: row.session_id,
    sessionRef: opaqueReference("hsref", row.session_id),
    userId: row.user_id,
    userName: row.name,
    workspaceId,
    membershipRole: membership.role,
  };
}

export async function humanSessionStatus(headers: Headers) {
  return withPostgresTransaction(async (client) => {
    await assertHumanRuntimeSchemaReady(client);
    const { row, token } = await lockSession(client, headers);
    const memberships = await client.query<MembershipRow>(
      `SELECT workspace_id,user_id,role,status FROM workspace_memberships
      WHERE user_id=$1 AND status='active' ORDER BY workspace_id`,
      [row.user_id],
    );
    await client.query("UPDATE human_sessions SET last_seen_at=$1 WHERE session_id=$2", [new Date().toISOString(), row.session_id]);
    return {
      status: 200,
      body: {
        ok: true,
        provider: "agentops-human-session",
        authenticated: true,
        user: publicUser(row),
        memberships: memberships.rows.map((item) => ({ workspace_id: item.workspace_id, role: item.role })),
        csrf_token: csrfToken(token),
        session_expires_at: row.expires_at,
        token_omitted: true,
      },
    };
  });
}

export async function logoutHumanSession(headers: Headers) {
  rejectMachineCredentials(headers);
  const origin = validateWriteOrigin(headers);
  return withPostgresTransaction(async (client) => {
    await assertHumanRuntimeSchemaReady(client);
    const { row, token } = await lockSession(client, headers);
    const suppliedCsrf = String(headers.get("x-agentops-csrf") || "").trim();
    if (!suppliedCsrf || !sameValue(suppliedCsrf, csrfToken(token))) {
      throw new ControlPlaneHttpError(403, "csrf_validation_failed", "A valid Human Session CSRF token is required.");
    }
    const now = new Date().toISOString();
    await client.query(
      "UPDATE human_sessions SET status='revoked',revoked_at=$1 WHERE session_id=$2 AND status='active'",
      [now, row.session_id],
    );
    const sessionRef = opaqueReference("hsref", row.session_id);
    await appendAudit(client, {
      actorType: "user",
      actorId: row.user_id,
      action: "human_auth.logout",
      entityType: "human_sessions",
      entityId: sessionRef,
      before: { status: "active" },
      after: { status: "revoked" },
      metadata: { credentials_omitted: true, session_id_omitted: true, token_omitted: true },
    });
    return {
      status: 200,
      body: {
        ok: true,
        provider: "agentops-human-session",
        authenticated: false,
        token_omitted: true,
      },
      setCookie: cookie("", origin, true),
    };
  });
}
