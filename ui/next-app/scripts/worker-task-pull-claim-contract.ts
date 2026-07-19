import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import process from "node:process";

import { Client, type Pool } from "pg";

import { errorPayload } from "../src/server/controlPlane/http";

const WORKSPACE = "ws_worker_contract";
const OTHER_WORKSPACE = "ws_worker_contract_other";
const AGENT_A = "agt_worker_contract_a";
const AGENT_B = "agt_worker_contract_b";
const AGENT_OBSERVER = "agt_worker_contract_observer";
const TOKEN_A = randomBytes(32).toString("base64url");
const TOKEN_B = randomBytes(32).toString("base64url");
const TOKEN_OBSERVER = randomBytes(32).toString("base64url");
const TOKEN_CLAIMER = randomBytes(32).toString("base64url");

type CapturedResponse = {
  status: number;
  body: Record<string, unknown>;
};

function tokenHash(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function scopedDsn(dsn: string, schema: string) {
  const url = new URL(dsn);
  url.searchParams.set("options", `-c search_path=${schema}`);
  return url.toString();
}

function gatewayHeaders(token: string, workspace: string, agentId: string, extra?: Record<string, string>) {
  return {
    "content-type": "application/json",
    authorization: `Bearer ${token}`,
    "x-agentops-workspace-id": workspace,
    "x-agentops-agent-id": agentId,
    ...extra,
  };
}

function claimRequest(
  token: string,
  agentId: string,
  body: Record<string, unknown> = {},
  extraHeaders?: Record<string, string>,
) {
  return new Request("http://127.0.0.1/api/mis/agent-gateway/tasks/contract/claim", {
    method: "POST",
    headers: gatewayHeaders(token, WORKSPACE, agentId, extraHeaders),
    body: JSON.stringify(body),
  });
}

async function main() {
  const baseDsn = String(process.env.AGENTOPS_POSTGRES_DSN || process.env.DATABASE_URL || "").trim();
  if (!baseDsn) throw new Error("postgres_dsn_required");
  const schema = `agentops_worker_contract_${randomBytes(8).toString("hex")}`;
  const quotedSchema = `"${schema}"`;
  const admin = new Client({
    connectionString: baseDsn,
    application_name: "agentops-worker-task-contract-setup",
  });
  let schemaCreated = false;
  try {
    await admin.connect();
    await admin.query(`CREATE SCHEMA ${quotedSchema}`);
    schemaCreated = true;
    await admin.query(`SET search_path TO ${quotedSchema}`);
    await admin.query(`
      CREATE TABLE agents(
        agent_id TEXT PRIMARY KEY,
        runtime_type TEXT NOT NULL DEFAULT 'mock',
        model_provider TEXT,
        model_name TEXT
      );
      CREATE TABLE agent_gateway_tokens(
        token_id TEXT PRIMARY KEY,
        token_hash TEXT NOT NULL UNIQUE,
        workspace_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        scopes_json TEXT NOT NULL,
        status TEXT NOT NULL,
        expires_at TEXT,
        last_used_at TEXT,
        last_heartbeat_at TEXT
      );
      CREATE TABLE agent_gateway_sessions(
        session_id TEXT PRIMARY KEY,
        parent_token_id TEXT,
        session_hash TEXT NOT NULL UNIQUE,
        workspace_id TEXT NOT NULL,
        agent_id TEXT NOT NULL,
        scopes_json TEXT NOT NULL,
        status TEXT NOT NULL,
        expires_at TEXT,
        revoked_at TEXT,
        last_used_at TEXT
      );
      CREATE TABLE tasks(
        task_id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        requester_id TEXT,
        owner_agent_id TEXT,
        collaborator_agent_ids TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL,
        priority TEXT NOT NULL,
        due_date TEXT,
        acceptance_criteria TEXT,
        risk_level TEXT NOT NULL,
        budget_limit_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE TABLE audit_logs(
        audit_id TEXT PRIMARY KEY,
        workspace_id TEXT,
        actor_type TEXT NOT NULL,
        actor_id TEXT,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        before_hash TEXT,
        after_hash TEXT,
        metadata_json TEXT,
        tamper_chain_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
      CREATE TABLE runtime_events(
        runtime_event_id TEXT PRIMARY KEY,
        runtime_connector_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        status TEXT NOT NULL,
        run_id TEXT,
        task_id TEXT,
        agent_id TEXT,
        model_name TEXT,
        latency_ms INTEGER,
        prompt_hash TEXT,
        input_summary TEXT,
        output_summary TEXT,
        error_message TEXT,
        raw_payload_hash TEXT,
        created_at TEXT NOT NULL
      );
    `);

    for (const agentId of [AGENT_A, AGENT_B, AGENT_OBSERVER]) {
      await admin.query(
        "INSERT INTO agents(agent_id,runtime_type,model_provider,model_name) VALUES($1,'mock','mock','contract')",
        [agentId],
      );
    }
    const tokenRows: Array<[string, string, string, string[]]> = [
      ["tok_worker_a", TOKEN_A, AGENT_A, ["tasks:read", "tasks:claim"]],
      ["tok_worker_b", TOKEN_B, AGENT_B, ["tasks:read", "tasks:claim"]],
      ["tok_worker_observer", TOKEN_OBSERVER, AGENT_OBSERVER, ["tasks:read"]],
      ["tok_worker_claimer", TOKEN_CLAIMER, AGENT_OBSERVER, ["tasks:claim"]],
    ];
    for (const [tokenId, token, agentId, scopes] of tokenRows) {
      await admin.query(
        `INSERT INTO agent_gateway_tokens(
          token_id,token_hash,workspace_id,agent_id,scopes_json,status
        ) VALUES($1,$2,$3,$4,$5,'active')`,
        [tokenId, tokenHash(token), WORKSPACE, agentId, JSON.stringify(scopes)],
      );
    }

    const tasks: Array<[string, string, string | null, string[], string, string]> = [
      ["tsk_pool", WORKSPACE, null, [], "planned", "2026-01-01T00:00:00.000Z"],
      ["tsk_owner_a", WORKSPACE, AGENT_A, [], "planned", "2026-01-01T00:01:00.000Z"],
      ["tsk_collaborator_a", WORKSPACE, AGENT_B, [AGENT_A], "backlog", "2026-01-01T00:02:00.000Z"],
      ["tsk_hidden_b", WORKSPACE, AGENT_B, [], "planned", "2026-01-01T00:03:00.000Z"],
      ["tsk_race", WORKSPACE, null, [], "planned", "2026-01-01T00:04:00.000Z"],
      ["tsk_completed", WORKSPACE, AGENT_A, [], "completed", "2026-01-01T00:05:00.000Z"],
      ["tsk_cross_tenant", OTHER_WORKSPACE, null, [], "planned", "2026-01-01T00:06:00.000Z"],
    ];
    for (const [taskId, workspace, owner, collaborators, status, createdAt] of tasks) {
      await admin.query(
        `INSERT INTO tasks(
          task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,
          priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at
        ) VALUES($1,$2,$3,NULL,NULL,$4,$5,$6,'medium',NULL,'Focused Worker contract','low',1,$7,$7)`,
        [taskId, workspace, `Worker contract ${taskId}`, owner, JSON.stringify(collaborators), status, createdAt],
      );
    }

    process.env.AGENTOPS_POSTGRES_DSN = scopedDsn(baseDsn, schema);
    process.env.AGENTOPS_POSTGRES_SSL = "0";
    const {
      claimAgentGatewayTask,
      pullAgentGatewayTasks,
    } = await import("../src/server/controlPlane/agentGatewayTasks");

    async function capturePull(request: Request): Promise<CapturedResponse> {
      try {
        return { status: 200, body: await pullAgentGatewayTasks(request) };
      } catch (error) {
        return errorPayload(error);
      }
    }

    async function captureClaim(request: Request, taskId: string): Promise<CapturedResponse> {
      try {
        return await claimAgentGatewayTask(request, taskId);
      } catch (error) {
        return errorPayload(error);
      }
    }

    const pulled = await capturePull(new Request(
      `http://127.0.0.1/api/mis/agent-gateway/tasks/pull?workspace_id=${WORKSPACE}&agent_id=${AGENT_A}&limit=50`,
      { headers: gatewayHeaders(TOKEN_A, WORKSPACE, AGENT_A) },
    ));
    assert.equal(pulled.status, 200);
    assert.equal(pulled.body.control_plane, "typescript_postgres");
    assert.deepEqual(
      (pulled.body.tasks as Array<{ task_id: string }>).map((row) => row.task_id),
      ["tsk_pool", "tsk_owner_a", "tsk_collaborator_a", "tsk_race"],
      "pull must return only bound owner/collaborator/unowned planned or backlog tasks in oldest-first order",
    );

    const wrongPullAgent = await capturePull(new Request(
      `http://127.0.0.1/api/mis/agent-gateway/tasks/pull?agent_id=${AGENT_B}`,
      { headers: gatewayHeaders(TOKEN_A, WORKSPACE, AGENT_A) },
    ));
    assert.equal(wrongPullAgent.status, 403);
    const wrongPullWorkspace = await capturePull(new Request(
      `http://127.0.0.1/api/mis/agent-gateway/tasks/pull?workspace_id=${OTHER_WORKSPACE}`,
      { headers: gatewayHeaders(TOKEN_A, WORKSPACE, AGENT_A) },
    ));
    assert.equal(wrongPullWorkspace.status, 403);
    const missingPullScope = await capturePull(new Request(
      "http://127.0.0.1/api/mis/agent-gateway/tasks/pull",
      { headers: gatewayHeaders(TOKEN_CLAIMER, WORKSPACE, AGENT_OBSERVER) },
    ));
    assert.equal(missingPullScope.status, 403, "tasks:read scope is mandatory");

    assert.equal((await captureClaim(
      claimRequest(TOKEN_A, AGENT_A, { agent_id: AGENT_B }),
      "tsk_pool",
    )).status, 403);
    assert.equal((await captureClaim(
      claimRequest(TOKEN_A, AGENT_A, { workspace_id: OTHER_WORKSPACE }),
      "tsk_pool",
    )).status, 403);
    assert.equal((await captureClaim(
      claimRequest(TOKEN_A, AGENT_A, {}, { "x-agentops-agent-id": AGENT_B }),
      "tsk_pool",
    )).status, 403);
    assert.equal((await captureClaim(
      claimRequest(TOKEN_A, AGENT_A, { task_id: "tsk_owner_a" }),
      "tsk_pool",
    )).status, 403);
    assert.equal((await captureClaim(
      claimRequest(TOKEN_OBSERVER, AGENT_OBSERVER),
      "tsk_pool",
    )).status, 403, "tasks:claim scope is mandatory");
    assert.equal((await captureClaim(
      claimRequest(TOKEN_A, AGENT_A, { padding: "x".repeat(5_000) }),
      "tsk_pool",
    )).status, 413, "claim body must be bounded");

    const ownerClaim = await captureClaim(claimRequest(TOKEN_A, AGENT_A), "tsk_owner_a");
    assert.equal(ownerClaim.status, 200);
    assert.equal(ownerClaim.body.claimed_by, AGENT_A);
    assert.equal((ownerClaim.body.task as { status: string }).status, "running");
    const ownerReplay = await captureClaim(claimRequest(TOKEN_A, AGENT_A), "tsk_owner_a");
    assert.equal(ownerReplay.status, 200);
    assert.equal(ownerReplay.body.already_claimed, true, "same-agent replay must be idempotent");

    const collaboratorClaim = await captureClaim(
      claimRequest(TOKEN_A, AGENT_A),
      "tsk_collaborator_a",
    );
    assert.equal(collaboratorClaim.status, 200);
    assert.equal((collaboratorClaim.body.task as { owner_agent_id: string }).owner_agent_id, AGENT_A);

    const [raceA, raceB] = await Promise.all([
      captureClaim(claimRequest(TOKEN_A, AGENT_A), "tsk_race"),
      captureClaim(claimRequest(TOKEN_B, AGENT_B), "tsk_race"),
    ]);
    const raceResults = [
      { ...raceA, agentId: AGENT_A, token: TOKEN_A },
      { ...raceB, agentId: AGENT_B, token: TOKEN_B },
    ];
    const winners = raceResults.filter((result) => result.status === 200);
    const losers = raceResults.filter((result) => result.status !== 200);
    assert.equal(winners.length, 1, "planned task must have exactly one claim winner");
    assert.equal(losers.length, 1);
    assert.ok([403, 409].includes(losers[0].status), "losing agent must fail closed");
    const raceReplay = await captureClaim(
      claimRequest(winners[0].token, winners[0].agentId),
      "tsk_race",
    );
    assert.equal(raceReplay.status, 200);
    assert.equal(raceReplay.body.already_claimed, true);

    assert.equal((await captureClaim(
      claimRequest(TOKEN_A, AGENT_A),
      "tsk_hidden_b",
    )).status, 403, "another agent's task must be forbidden");
    assert.equal((await captureClaim(
      claimRequest(TOKEN_A, AGENT_A),
      "tsk_cross_tenant",
    )).status, 404, "cross-tenant task identity must not be disclosed");
    assert.equal((await captureClaim(
      claimRequest(TOKEN_A, AGENT_A),
      "tsk_completed",
    )).status, 409, "terminal task cannot be claimed");

    const evidence = await admin.query<{
      pull_events: string;
      claim_events: string;
      pull_audits: string;
      claim_audits: string;
    }>(`
      SELECT
        (SELECT COUNT(*)::text FROM runtime_events WHERE event_type='task.pull') AS pull_events,
        (SELECT COUNT(*)::text FROM runtime_events WHERE event_type='task.claim') AS claim_events,
        (SELECT COUNT(*)::text FROM audit_logs WHERE action='agent_gateway.task_pull') AS pull_audits,
        (SELECT COUNT(*)::text FROM audit_logs WHERE action='agent_gateway.task_claim') AS claim_audits
    `);
    assert.deepEqual(evidence.rows[0], {
      pull_events: "1",
      claim_events: "3",
      pull_audits: "1",
      claim_audits: "3",
    }, "successful pull and first claims must write one runtime/audit evidence pair; replays must not duplicate it");
    const storedEvidence = JSON.stringify((await admin.query(
      "SELECT actor_id,action,entity_id,metadata_json FROM audit_logs ORDER BY created_at",
    )).rows) + JSON.stringify((await admin.query(
      "SELECT event_type,task_id,agent_id,input_summary,output_summary,error_message FROM runtime_events ORDER BY created_at",
    )).rows);
    for (const token of [TOKEN_A, TOKEN_B, TOKEN_OBSERVER, TOKEN_CLAIMER]) {
      assert.equal(storedEvidence.includes(token), false, "raw credentials must be omitted from evidence");
    }

    process.stdout.write(`${JSON.stringify({
      ok: true,
      contract: "nextjs_postgres_worker_task_pull_claim_v1",
      checks: {
        worker_client_shape_compatible: true,
        scope_workspace_agent_binding: true,
        owner_collaborator_visibility: true,
        bounded_claim_body: true,
        planned_to_running_single_winner: true,
        same_agent_replay_idempotent: true,
        cross_tenant_and_other_agent_fail_closed: true,
        audit_and_runtime_evidence: true,
      },
      credentials_omitted: true,
    })}\n`);
  } finally {
    const pool = (globalThis as typeof globalThis & { __agentOpsControlPlanePool?: Pool })
      .__agentOpsControlPlanePool;
    await pool?.end().catch(() => undefined);
    if (schemaCreated) {
      await admin.query("SET search_path TO public").catch(() => undefined);
      await admin.query(`DROP SCHEMA ${quotedSchema} CASCADE`).catch(() => undefined);
    }
    await admin.end().catch(() => undefined);
  }
}

main().catch((error: unknown) => {
  const code = error instanceof Error && /^[a-z0-9_]+$/.test(error.message)
    ? error.message
    : "worker_task_pull_claim_contract_failed";
  process.stdout.write(`${JSON.stringify({ ok: false, error: code, credentials_omitted: true })}\n`);
  process.exitCode = 1;
});
