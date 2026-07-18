import { createHash } from "node:crypto";
import type { PoolClient } from "pg";

import { ControlPlaneHttpError } from "./http";
import { appendAudit } from "./ledger";

type CredentialRow = {
  credential_type: "token" | "session";
  credential_id: string;
  parent_token_id: string | null;
  workspace_id: string;
  agent_id: string;
  scopes_json: string;
  status: string;
  expires_at: string | null;
};

type ParentTokenRow = {
  token_id: string;
  workspace_id: string;
  agent_id: string;
  status: string;
  expires_at: string | null;
};

export type AgentGatewayIdentity = {
  mode: "agent_token" | "agent_session";
  credentialId: string;
  parentTokenId: string | null;
  workspaceId: string;
  agentId: string;
  scopes: string[];
};

function bearerToken(headers: Headers) {
  const authorization = String(headers.get("authorization") || "").trim();
  if (authorization.toLowerCase().startsWith("bearer ")) return authorization.slice(7).trim();
  return String(headers.get("x-agentops-api-key") || "").trim();
}

function scopes(value: string) {
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map((item) => String(item)) : [];
  } catch {
    return [];
  }
}

export function agentGatewayTimestampExpired(
  value: string | null,
  nowMs = Date.now(),
  allowMissing = false,
) {
  if (value === null) return !allowMissing;
  const expiresAt = Date.parse(value);
  return !Number.isFinite(expiresAt) || expiresAt <= nowMs;
}

export async function authenticateAgentGateway(
  client: PoolClient,
  headers: Headers,
  requiredScope: string,
): Promise<AgentGatewayIdentity> {
  const supplied = bearerToken(headers);
  if (!supplied) {
    throw new ControlPlaneHttpError(401, "unauthorized", "Agent Gateway token or session is required.");
  }
  const hash = createHash("sha256").update(supplied, "utf8").digest("hex");
  const tokenResult = await client.query<CredentialRow>(
    `SELECT 'token'::text AS credential_type, token_id AS credential_id, NULL::text AS parent_token_id,
      workspace_id,agent_id,scopes_json,status,expires_at
    FROM agent_gateway_tokens WHERE token_hash=$1 FOR UPDATE`,
    [hash],
  );
  let row = tokenResult.rows[0];
  let sessionParent: ParentTokenRow | undefined;
  if (!row) {
    const sessionCandidateResult = await client.query<CredentialRow>(
      `SELECT 'session'::text AS credential_type, session_id AS credential_id,parent_token_id,
        workspace_id,agent_id,scopes_json,status,expires_at
      FROM agent_gateway_sessions WHERE session_hash=$1`,
      [hash],
    );
    const sessionCandidate = sessionCandidateResult.rows[0];
    if (sessionCandidate?.parent_token_id) {
      const parentResult = await client.query<ParentTokenRow>(
        `SELECT token_id,workspace_id,agent_id,status,expires_at
        FROM agent_gateway_tokens WHERE token_id=$1 FOR UPDATE`,
        [sessionCandidate.parent_token_id],
      );
      sessionParent = parentResult.rows[0];
    }
    if (sessionCandidate) {
      const sessionResult = await client.query<CredentialRow>(
        `SELECT 'session'::text AS credential_type, session_id AS credential_id,parent_token_id,
          workspace_id,agent_id,scopes_json,status,expires_at
        FROM agent_gateway_sessions WHERE session_id=$1 AND session_hash=$2 FOR UPDATE`,
        [sessionCandidate.credential_id, hash],
      );
      row = sessionResult.rows[0];
      if (row?.parent_token_id !== sessionCandidate.parent_token_id) sessionParent = undefined;
    }
  }
  if (!row) {
    throw new ControlPlaneHttpError(401, "unauthorized", "Agent Gateway token is not recognized.");
  }
  if (row.status !== "active") {
    throw new ControlPlaneHttpError(401, "unauthorized", `Agent Gateway ${row.credential_type} is ${row.status}.`);
  }
  if (agentGatewayTimestampExpired(row.expires_at, Date.now(), row.credential_type === "token")) {
    const table = row.credential_type === "token" ? "agent_gateway_tokens" : "agent_gateway_sessions";
    const idColumn = row.credential_type === "token" ? "token_id" : "session_id";
    await client.query(`UPDATE ${table} SET status='expired' WHERE ${idColumn}=$1 AND status='active'`, [row.credential_id]);
    await appendAudit(client, {
      actorType: "system",
      actorId: "agent-gateway-auth",
      action: `agent_gateway.${row.credential_type}_expired`,
      entityType: table,
      entityId: row.credential_id,
      before: row,
      after: { ...row, status: "expired" },
      metadata: { token_omitted: true },
    });
    throw new ControlPlaneHttpError(
      401,
      "unauthorized",
      `Agent Gateway ${row.credential_type} is expired.`,
      true,
    );
  }
  if (row.credential_type === "session") {
    if (!row.parent_token_id || !sessionParent || sessionParent.token_id !== row.parent_token_id) {
      await client.query(
        "UPDATE agent_gateway_sessions SET status='revoked',revoked_at=$1 WHERE session_id=$2 AND status='active'",
        [new Date().toISOString(), row.credential_id],
      );
      await appendAudit(client, {
        actorType: "system",
        actorId: "agent-gateway-auth",
        action: "agent_gateway.session_parent_missing",
        entityType: "agent_gateway_sessions",
        entityId: row.credential_id,
        before: row,
        after: { ...row, status: "revoked" },
        metadata: { parent_token_id: row.parent_token_id, token_omitted: true },
      });
      throw new ControlPlaneHttpError(401, "unauthorized", "Agent Gateway session parent token is missing.", true);
    }
    if (sessionParent.status !== "active") {
      await client.query(
        "UPDATE agent_gateway_sessions SET status='revoked',revoked_at=$1 WHERE session_id=$2 AND status='active'",
        [new Date().toISOString(), row.credential_id],
      );
      await appendAudit(client, {
        actorType: "system",
        actorId: "agent-gateway-auth",
        action: "agent_gateway.session_parent_revoked",
        entityType: "agent_gateway_sessions",
        entityId: row.credential_id,
        before: row,
        after: { ...row, status: "revoked" },
        metadata: {
          parent_token_id: row.parent_token_id,
          parent_status: sessionParent.status,
          token_omitted: true,
        },
      });
      throw new ControlPlaneHttpError(
        401,
        "unauthorized",
        `Agent Gateway session parent token is ${sessionParent.status}.`,
        true,
      );
    }
    if (agentGatewayTimestampExpired(sessionParent.expires_at, Date.now(), true)) {
      await client.query(
        "UPDATE agent_gateway_tokens SET status='expired' WHERE token_id=$1 AND status='active'",
        [sessionParent.token_id],
      );
      await client.query(
        "UPDATE agent_gateway_sessions SET status='expired' WHERE session_id=$1 AND status='active'",
        [row.credential_id],
      );
      await appendAudit(client, {
        actorType: "system",
        actorId: "agent-gateway-auth",
        action: "agent_gateway.session_parent_expired",
        entityType: "agent_gateway_sessions",
        entityId: row.credential_id,
        before: row,
        after: { ...row, status: "expired" },
        metadata: { parent_token_id: sessionParent.token_id, token_omitted: true },
      });
      throw new ControlPlaneHttpError(401, "unauthorized", "Agent Gateway session parent token is expired.", true);
    }
    if (sessionParent.workspace_id !== row.workspace_id || sessionParent.agent_id !== row.agent_id) {
      await client.query(
        "UPDATE agent_gateway_sessions SET status='revoked',revoked_at=$1 WHERE session_id=$2 AND status='active'",
        [new Date().toISOString(), row.credential_id],
      );
      await appendAudit(client, {
        actorType: "system",
        actorId: "agent-gateway-auth",
        action: "agent_gateway.session_parent_binding_mismatch",
        entityType: "agent_gateway_sessions",
        entityId: row.credential_id,
        before: row,
        after: { ...row, status: "revoked" },
        metadata: { parent_token_id: sessionParent.token_id, token_omitted: true },
      });
      throw new ControlPlaneHttpError(
        401,
        "unauthorized",
        "Agent Gateway session binding no longer matches its parent token.",
        true,
      );
    }
  }
  const granted = scopes(row.scopes_json);
  if (!granted.includes(requiredScope)) {
    throw new ControlPlaneHttpError(403, "forbidden", `Agent credential is missing required scope: ${requiredScope}`);
  }
  const table = row.credential_type === "token" ? "agent_gateway_tokens" : "agent_gateway_sessions";
  const idColumn = row.credential_type === "token" ? "token_id" : "session_id";
  await client.query(`UPDATE ${table} SET last_used_at=$1 WHERE ${idColumn}=$2`, [new Date().toISOString(), row.credential_id]);
  return {
    mode: row.credential_type === "token" ? "agent_token" : "agent_session",
    credentialId: row.credential_id,
    parentTokenId: row.parent_token_id,
    workspaceId: row.workspace_id,
    agentId: row.agent_id,
    scopes: granted,
  };
}

export function enforceWorkspaceBinding(
  identity: AgentGatewayIdentity,
  input: { header?: string | null; query?: string | null; body?: unknown },
) {
  for (const requested of [input.header, input.query, typeof input.body === "string" ? input.body : null]) {
    if (requested && requested.trim() !== identity.workspaceId) {
      throw new ControlPlaneHttpError(403, "forbidden", "Agent credential cannot act in another workspace.");
    }
  }
}
