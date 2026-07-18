import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import process from "node:process";
import { Client } from "pg";

const WORKSPACE_ID = "ws_worker_direct";
const OTHER_WORKSPACE_ID = "ws_worker_other";
const AGENT_ID = "agt_worker_direct";
const OTHER_AGENT_ID = "agt_worker_other";
const OBSERVER_AGENT_ID = "agt_worker_observer";
const TASK_ID = "tsk_worker_direct";
const RUN_ID = "run_gw_worker_direct";
const RAW_TOKEN = `agtok_contract_${randomBytes(24).toString("hex")}`;
const RAW_SESSION = `agtsess_contract_${randomBytes(24).toString("hex")}`;
const OTHER_TOKEN = `agtok_contract_${randomBytes(24).toString("hex")}`;
const OBSERVER_TOKEN = `agtok_contract_${randomBytes(24).toString("hex")}`;
const LIMITED_TOKEN = `agtok_contract_${randomBytes(24).toString("hex")}`;
const SENSITIVE_VALUE = `sk-contract-${randomBytes(16).toString("hex")}`;

function tokenHash(value: string) {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

function scopedDsn(dsn: string, schema: string) {
  const url = new URL(dsn);
  url.searchParams.set("options", `-csearch_path=${schema}`);
  return url.toString();
}

function request(token: string, body: Record<string, unknown>, workspaceId = WORKSPACE_ID, declaredLength?: number) {
  const raw = JSON.stringify(body);
  const headers = new Headers({
    authorization: `Bearer ${token}`,
    "content-type": "application/json",
    "x-agentops-workspace-id": workspaceId,
  });
  if (declaredLength !== undefined) headers.set("content-length", String(declaredLength));
  return new Request("http://127.0.0.1/api/mis/agent-gateway/contract", {
    method: "POST",
    headers,
    body: raw,
  });
}

async function expectHttpError(work: () => Promise<unknown>, status: number, code: string) {
  try {
    await work();
  } catch (error) {
    const candidate = error as { status?: number; code?: string };
    assert.equal(candidate.status, status);
    assert.equal(candidate.code, code);
    return;
  }
  assert.fail(`expected_${code}`);
}

async function createSchema(client: Client) {
  await client.query(`
    CREATE TABLE users(
      user_id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      email TEXT NOT NULL,
      role TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE agents(
      agent_id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      role TEXT NOT NULL,
      description TEXT,
      runtime_type TEXT NOT NULL,
      model_provider TEXT,
      model_name TEXT,
      status TEXT NOT NULL,
      permission_level TEXT NOT NULL,
      allowed_tools TEXT NOT NULL,
      budget_limit_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
      owner_user_id TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE tasks(
      task_id TEXT PRIMARY KEY,
      workspace_id TEXT NOT NULL,
      owner_agent_id TEXT,
      collaborator_agent_ids TEXT NOT NULL DEFAULT '[]'
    );
    CREATE TABLE runs(
      run_id TEXT PRIMARY KEY,
      workspace_id TEXT NOT NULL,
      task_id TEXT NOT NULL,
      agent_id TEXT NOT NULL
    );
    CREATE TABLE agent_gateway_tokens(
      token_id TEXT PRIMARY KEY,
      token_hash TEXT NOT NULL UNIQUE,
      workspace_id TEXT NOT NULL,
      agent_id TEXT NOT NULL,
      scopes_json TEXT NOT NULL,
      status TEXT NOT NULL,
      label TEXT,
      heartbeat_timeout_sec INTEGER NOT NULL DEFAULT 300,
      created_at TEXT NOT NULL,
      expires_at TEXT,
      revoked_at TEXT,
      last_used_at TEXT,
      last_heartbeat_at TEXT
    );
    CREATE TABLE agent_gateway_sessions(
      session_id TEXT PRIMARY KEY,
      session_hash TEXT NOT NULL UNIQUE,
      parent_token_id TEXT,
      workspace_id TEXT NOT NULL,
      agent_id TEXT NOT NULL,
      scopes_json TEXT NOT NULL,
      status TEXT NOT NULL,
      created_at TEXT NOT NULL,
      expires_at TEXT NOT NULL,
      revoked_at TEXT,
      last_used_at TEXT
    );
    CREATE TABLE audit_logs(
      audit_id TEXT PRIMARY KEY,
      actor_type TEXT NOT NULL,
      actor_id TEXT,
      action TEXT NOT NULL,
      entity_type TEXT NOT NULL,
      entity_id TEXT NOT NULL,
      before_hash TEXT,
      after_hash TEXT,
      metadata_json TEXT NOT NULL DEFAULT '{}',
      tamper_chain_hash TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE runtime_events(
      runtime_event_id TEXT PRIMARY KEY,
      runtime_connector_id TEXT,
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
}

async function seed(client: Client) {
  const now = new Date();
  const nowText = now.toISOString();
  const expiresAt = new Date(now.getTime() + 60 * 60 * 1000).toISOString();
  await client.query(
    "INSERT INTO users(user_id,name,email,role,created_at) VALUES($1,$1,$2,'founder',$3)",
    ["usr_founder", "worker-direct@example.local", nowText],
  );
  for (const agentId of [AGENT_ID, OTHER_AGENT_ID, OBSERVER_AGENT_ID]) {
    await client.query(
      `INSERT INTO agents(
        agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,
        allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at
      ) VALUES($1,$1,'Worker','Worker direct contract','mock','mock','mock','idle','standard','[]',5,'usr_founder',$2,$2)`,
      [agentId, nowText],
    );
  }
  const tokenRows: Array<[string, string, string, string, string[]]> = [
    ["tok_worker_direct", RAW_TOKEN, WORKSPACE_ID, AGENT_ID, ["agents:write", "agents:heartbeat", "audit:write"]],
    ["tok_worker_other", OTHER_TOKEN, OTHER_WORKSPACE_ID, OTHER_AGENT_ID, ["agents:write", "agents:heartbeat", "audit:write"]],
    ["tok_worker_observer", OBSERVER_TOKEN, WORKSPACE_ID, OBSERVER_AGENT_ID, ["audit:write"]],
    ["tok_worker_limited", LIMITED_TOKEN, WORKSPACE_ID, AGENT_ID, ["agents:heartbeat"]],
  ];
  for (const [tokenId, rawToken, workspaceId, agentId, scopes] of tokenRows) {
    await client.query(
      `INSERT INTO agent_gateway_tokens(
        token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,
        created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at
      ) VALUES($1,$2,$3,$4,$5,'active','worker-direct-contract',60,$6,$7,NULL,NULL,NULL)`,
      [tokenId, tokenHash(rawToken), workspaceId, agentId, JSON.stringify(scopes), nowText, expiresAt],
    );
  }
  await client.query(
    `INSERT INTO agent_gateway_sessions(
      session_id,session_hash,parent_token_id,workspace_id,agent_id,scopes_json,status,created_at,expires_at,revoked_at,last_used_at
    ) VALUES('ses_worker_direct',$1,'tok_worker_direct',$2,$3,$4,'active',$5,$6,NULL,NULL)`,
    [tokenHash(RAW_SESSION), WORKSPACE_ID, AGENT_ID, JSON.stringify(["agents:heartbeat"]), nowText, expiresAt],
  );
  await client.query(
    "INSERT INTO tasks(task_id,workspace_id,owner_agent_id,collaborator_agent_ids) VALUES($1,$2,$3,$4)",
    [TASK_ID, WORKSPACE_ID, AGENT_ID, JSON.stringify([OBSERVER_AGENT_ID])],
  );
  await client.query(
    "INSERT INTO runs(run_id,workspace_id,task_id,agent_id) VALUES($1,$2,$3,$4)",
    [RUN_ID, WORKSPACE_ID, TASK_ID, AGENT_ID],
  );
  await client.query(
    "INSERT INTO runs(run_id,workspace_id,task_id,agent_id) VALUES('run_gw_worker_observer',$1,$2,$3)",
    [WORKSPACE_ID, TASK_ID, OBSERVER_AGENT_ID],
  );
  await client.query(
    "INSERT INTO tasks(task_id,workspace_id,owner_agent_id,collaborator_agent_ids) VALUES('tsk_worker_other',$1,$2,'[]')",
    [OTHER_WORKSPACE_ID, OTHER_AGENT_ID],
  );
  await client.query(
    "INSERT INTO runs(run_id,workspace_id,task_id,agent_id) VALUES('run_gw_worker_other',$1,'tsk_worker_other',$2)",
    [OTHER_WORKSPACE_ID, OTHER_AGENT_ID],
  );
}

async function main() {
  const dsn = String(process.env.AGENTOPS_POSTGRES_DSN || process.env.DATABASE_URL || "").trim();
  if (!dsn) throw new Error("postgres_dsn_required");
  const schema = `agentops_worker_direct_${randomBytes(8).toString("hex")}`;
  const quotedSchema = `"${schema}"`;
  const admin = new Client({ connectionString: dsn, application_name: "agentops-worker-direct-contract-admin" });
  let schemaCreated = false;
  try {
    await admin.connect();
    await admin.query(`CREATE SCHEMA ${quotedSchema}`);
    schemaCreated = true;
    await admin.query(`SET search_path TO ${quotedSchema}`);
    await createSchema(admin);
    await seed(admin);

    process.env.AGENTOPS_POSTGRES_DSN = scopedDsn(dsn, schema);
    process.env.AGENTOPS_POSTGRES_SSL = "0";
    const {
      emitAgentGatewayAudit,
      recordAgentGatewayHeartbeat,
      registerAgentGatewayWorker,
    } = await import("../src/server/controlPlane/agentGatewayHeartbeatAudit");

    const registerBody = {
      workspace_id: WORKSPACE_ID,
      agent_id: AGENT_ID,
      name: "Local Agent Worker",
      role: "Local Hermes Adapter Worker",
      runtime_type: "hermes",
      model_provider: "hermes",
      model_name: "hermes",
      permission_level: "standard",
      allowed_tools: ["agent_gateway.task", "hermes.execute", "agent_gateway.audit"],
      budget_limit_usd: 5,
      description: "Installable worker daemon.",
      owner_user_id: "usr_forged",
    };
    const registered = await registerAgentGatewayWorker(request(RAW_TOKEN, registerBody));
    assert.equal(registered.status, 200);
    assert.equal(registered.body.outcome, "updated");
    assert.equal(registered.body.agent.agent_id, AGENT_ID);
    assert.equal(registered.body.agent.owner_user_id, "usr_founder", "caller cannot replace the server-owned owner binding");
    const replayedRegister = await registerAgentGatewayWorker(request(RAW_TOKEN, registerBody));
    assert.equal(replayedRegister.status, 200);
    assert.equal(replayedRegister.body.outcome, "unchanged");

    await expectHttpError(
      () => registerAgentGatewayWorker(request(RAW_TOKEN, { ...registerBody, agent_id: OTHER_AGENT_ID })),
      403,
      "forbidden",
    );
    await expectHttpError(
      () => registerAgentGatewayWorker(request(RAW_TOKEN, { ...registerBody, workspace_id: OTHER_WORKSPACE_ID })),
      403,
      "forbidden",
    );

    const heartbeat = await recordAgentGatewayHeartbeat(request(RAW_TOKEN, {
      workspace_id: WORKSPACE_ID,
      agent_id: AGENT_ID,
      status: "running",
      summary: `Bearer ${SENSITIVE_VALUE}`,
      runtime_type: "hermes",
    }));
    assert.equal(heartbeat.status, 200);
    assert.equal(heartbeat.body.agent_id, AGENT_ID);
    assert.equal(heartbeat.body.status, "running");
    const agentState = await admin.query<{ status: string }>("SELECT status FROM agents WHERE agent_id=$1", [AGENT_ID]);
    assert.equal(agentState.rows[0]?.status, "running");
    const tokenState = await admin.query<{ last_heartbeat_at: string | null }>(
      "SELECT last_heartbeat_at FROM agent_gateway_tokens WHERE token_id='tok_worker_direct'",
    );
    assert.ok(tokenState.rows[0]?.last_heartbeat_at);

    const sessionHeartbeat = await recordAgentGatewayHeartbeat(request(RAW_SESSION, {
      workspace_id: WORKSPACE_ID,
      agent_id: AGENT_ID,
      status: "idle",
      summary: "Session heartbeat.",
    }));
    assert.equal(sessionHeartbeat.status, 200);
    const sessionState = await admin.query<{ last_used_at: string | null }>(
      "SELECT last_used_at FROM agent_gateway_sessions WHERE session_id='ses_worker_direct'",
    );
    assert.ok(sessionState.rows[0]?.last_used_at);

    await expectHttpError(
      () => recordAgentGatewayHeartbeat(request(RAW_TOKEN, { workspace_id: WORKSPACE_ID, agent_id: OTHER_AGENT_ID })),
      403,
      "forbidden",
    );
    await expectHttpError(
      () => recordAgentGatewayHeartbeat(request(RAW_TOKEN, { workspace_id: OTHER_WORKSPACE_ID }, WORKSPACE_ID)),
      403,
      "forbidden",
    );
    await expectHttpError(
      () => recordAgentGatewayHeartbeat(request(RAW_TOKEN, { workspace_id: 123 })),
      400,
      "workspace_id_invalid",
    );
    await expectHttpError(
      () => recordAgentGatewayHeartbeat(request(RAW_TOKEN, {}, WORKSPACE_ID, 9_000)),
      413,
      "request_too_large",
    );

    const emitted = await emitAgentGatewayAudit(request(RAW_TOKEN, {
      workspace_id: WORKSPACE_ID,
      agent_id: AGENT_ID,
      actor_type: "system",
      actor_id: OTHER_AGENT_ID,
      action: "agent_worker.task_processed",
      entity_type: "runs",
      entity_id: RUN_ID,
      task_id: TASK_ID,
      run_id: RUN_ID,
      after: { status: "completed", raw_response: SENSITIVE_VALUE },
      metadata: {
        adapter: "hermes",
        ok: true,
        authorization: `Bearer ${SENSITIVE_VALUE}`,
        raw_prompt: SENSITIVE_VALUE,
        token: SENSITIVE_VALUE,
        note: `password=${SENSITIVE_VALUE}`,
      },
    }));
    assert.equal(emitted.status, 201);
    assert.deepEqual(emitted.body, {
      emitted: true,
      entity_type: "runs",
      entity_id: RUN_ID,
      token_omitted: true,
    });
    const auditResult = await admin.query<{
      actor_type: string;
      actor_id: string;
      metadata_json: string;
      tamper_chain_hash: string | null;
    }>(
      "SELECT actor_type,actor_id,metadata_json,tamper_chain_hash FROM audit_logs WHERE action='agent_worker.task_processed'",
    );
    assert.equal(auditResult.rowCount, 1);
    assert.equal(auditResult.rows[0]?.actor_type, "agent");
    assert.equal(auditResult.rows[0]?.actor_id, AGENT_ID);
    assert.ok(auditResult.rows[0]?.tamper_chain_hash);
    const auditMetadataText = auditResult.rows[0]?.metadata_json || "";
    const auditMetadata = JSON.parse(auditMetadataText) as Record<string, unknown>;
    assert.equal(auditMetadata.workspace_id, WORKSPACE_ID);
    assert.equal(auditMetadata.agent_id, AGENT_ID);
    assert.equal(auditMetadata.raw_metadata_omitted, true);
    assert.ok(Number(auditMetadata.omitted_metadata_fields) >= 3);
    assert.ok(!auditMetadataText.includes(SENSITIVE_VALUE));
    assert.ok(!auditMetadataText.includes("authorization"));
    assert.ok(!auditMetadataText.includes("raw_prompt"));

    const collaboratorAudit = await emitAgentGatewayAudit(request(OBSERVER_TOKEN, {
      workspace_id: WORKSPACE_ID,
      agent_id: OBSERVER_AGENT_ID,
      action: "scope_matrix.observer_checked",
      entity_type: "tasks",
      entity_id: TASK_ID,
      metadata: { result: "observed" },
    }));
    assert.equal(collaboratorAudit.status, 201);

    await expectHttpError(
      () => emitAgentGatewayAudit(request(RAW_TOKEN, {
        workspace_id: WORKSPACE_ID,
        agent_id: AGENT_ID,
        action: "forged.run",
        entity_type: "runs",
        entity_id: "run_gw_worker_observer",
      })),
      403,
      "forbidden",
    );
    await expectHttpError(
      () => emitAgentGatewayAudit(request(RAW_TOKEN, {
        workspace_id: WORKSPACE_ID,
        agent_id: AGENT_ID,
        action: "cross.workspace",
        entity_type: "runs",
        entity_id: "run_gw_worker_other",
      })),
      404,
      "run_not_found",
    );
    await expectHttpError(
      () => emitAgentGatewayAudit(request(RAW_TOKEN, {
        workspace_id: WORKSPACE_ID,
        agent_id: AGENT_ID,
        action: "mismatched.task",
        entity_type: "runs",
        entity_id: RUN_ID,
        run_id: RUN_ID,
        task_id: "tsk_worker_other",
      })),
      403,
      "forbidden",
    );
    await expectHttpError(
      () => emitAgentGatewayAudit(request(LIMITED_TOKEN, {
        workspace_id: WORKSPACE_ID,
        agent_id: AGENT_ID,
        action: "missing.scope",
        entity_type: "runs",
        entity_id: RUN_ID,
      })),
      403,
      "forbidden",
    );
    await expectHttpError(
      () => emitAgentGatewayAudit(request(RAW_TOKEN, {
        workspace_id: WORKSPACE_ID,
        agent_id: AGENT_ID,
        action: "unknown.entity",
        entity_type: "arbitrary_table",
        entity_id: AGENT_ID,
      })),
      400,
      "entity_type_invalid",
    );

    await admin.query(
      `INSERT INTO agent_gateway_tokens(
        token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,
        created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at
      ) SELECT 'tok_worker_cross_binding',$1,$2,$3,$4,'active','cross-binding',60,created_at,expires_at,NULL,NULL,NULL
        FROM agent_gateway_tokens WHERE token_id='tok_worker_direct'`,
      [tokenHash(`agtok_contract_${randomBytes(24).toString("hex")}`), OTHER_WORKSPACE_ID, AGENT_ID, JSON.stringify(["agents:heartbeat"])],
    );
    await expectHttpError(
      () => recordAgentGatewayHeartbeat(request(RAW_TOKEN, { workspace_id: WORKSPACE_ID, agent_id: AGENT_ID })),
      409,
      "agent_workspace_binding_conflict",
    );

    const storedEvidence = await admin.query<{ payload: string }>(`
      SELECT COALESCE(string_agg(payload, ' '), '') AS payload FROM (
        SELECT metadata_json AS payload FROM audit_logs
        UNION ALL
        SELECT COALESCE(output_summary, '') AS payload FROM runtime_events
      ) evidence
    `);
    assert.ok(!(storedEvidence.rows[0]?.payload || "").includes(SENSITIVE_VALUE));
    process.stdout.write(`${JSON.stringify({
      ok: true,
      contract: "agent_gateway_worker_direct_next_postgres_v1",
      checks: {
        register_worker_semantics: true,
        exact_scopes: true,
        workspace_agent_binding: true,
        heartbeat_agent_and_parent_token_updated: true,
        run_task_entity_binding: true,
        collaborator_task_audit: true,
        server_derived_actor: true,
        bounded_body: true,
        sensitive_metadata_omitted: true,
        append_audit_chain: true,
      },
      credentials_omitted: true,
    })}\n`);
  } finally {
    await globalThis.__agentOpsControlPlanePool?.end().catch(() => undefined);
    globalThis.__agentOpsControlPlanePool = undefined;
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
    : "agent_gateway_worker_direct_contract_failed";
  process.stdout.write(`${JSON.stringify({ ok: false, error: code, credentials_omitted: true })}\n`);
  process.exitCode = 1;
});
