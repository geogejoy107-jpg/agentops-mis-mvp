import assert from "node:assert/strict";
import { createHash, createHmac, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { Client, type Pool, type PoolClient } from "pg";
import { NextRequest } from "next/server";

import { GET as getApprovalsRoute } from "../app/api/mis/approvals/route";
import { GET as getAuditRoute } from "../app/api/mis/audit/route";
import { GET as getDashboardMetricsRoute } from "../app/api/mis/dashboard/metrics/route";
import { GET as getRunsRoute } from "../app/api/mis/runs/route";
import { GET as getTasksRoute } from "../app/api/mis/tasks/route";

import { authenticateHumanMember } from "../src/server/controlPlane/humanSession";
import {
  HUMAN_MEMORY_SCHEMA_CHECKSUM,
  HUMAN_MEMORY_SCHEMA_COMPONENT,
  HUMAN_MEMORY_SCHEMA_CONTRACT,
  HUMAN_MEMORY_SCHEMA_ONLINE_INDEX_CHECKSUM,
  HUMAN_MEMORY_SCHEMA_VERSION,
  HUMAN_MEMORY_SCHEMA_V1_CHECKSUM,
} from "../src/server/controlPlane/schemaReadiness";
import {
  listWorkspaceApprovals,
  listWorkspaceAudit,
  listWorkspaceRuns,
  listWorkspaceTasks,
  workspaceDashboardMetrics,
} from "../src/server/controlPlane/workspaceReadModels";

const BASE_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260718_human_session_memory_review.sql", import.meta.url),
);
const UPGRADE_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260719_workspace_read_models_v2.sql", import.meta.url),
);
const ONLINE_INDEX_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260719_workspace_read_models_v2_online_indexes.sql", import.meta.url),
);
const WORKSPACE_A = "ws_read_model_a";
const WORKSPACE_B = "ws_read_model_b";
const USER_SINGLE = "usr_read_model_single";
const USER_MULTI = "usr_read_model_multi";
const SESSION_TOKEN_SINGLE = randomBytes(32).toString("base64url");
const SESSION_TOKEN_MULTI = randomBytes(32).toString("base64url");
const SESSION_HMAC_KEY = `workspace-read-model-contract-${randomBytes(32).toString("hex")}`;
const AGENT_OWNER_A = "agt_read_owner_a";
const AGENT_TOKEN_A = "agt_read_token_a";
const AGENT_SESSION_A = "agt_read_session_a";
const AGENT_REVOKED_A = "agt_read_revoked_a";
const RUN_AGENTS_A = Array.from({ length: 7 }, (_, index) => `agt_read_run_a_${index + 1}`);

type HttpResult<T> = { status: number; body: T };
type Row = Record<string, unknown>;
type RunList = (
  headers: Headers,
  workspaceId: unknown,
  suppliedLimit: unknown,
  filters?: { taskId?: string | null; agentId?: string | null },
) => Promise<HttpResult<Row[]>>;

function output(payload: Record<string, unknown>) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function sslEnabled() {
  return ["1", "true", "require", "required", "on"]
    .includes(String(process.env.AGENTOPS_POSTGRES_SSL || "").trim().toLowerCase());
}

function scopedDsn(dsn: string, schema: string) {
  const url = new URL(dsn);
  url.searchParams.set("options", `-csearch_path=${schema}`);
  return url.toString();
}

function sessionHash(token: string) {
  return createHmac("sha256", SESSION_HMAC_KEY)
    .update(`session:${token}`, "utf8")
    .digest("hex");
}

function humanHeaders(token: string, workspaceId?: string) {
  const headers = new Headers({ cookie: `agentops_human_session=${encodeURIComponent(token)}` });
  if (workspaceId) headers.set("x-agentops-workspace-id", workspaceId);
  return headers;
}

async function expectHttpError(
  work: () => Promise<unknown>,
  expectedStatus: number,
  expectedCode: string,
) {
  try {
    await work();
  } catch (error) {
    const candidate = error as { status?: number; code?: string };
    assert.equal(candidate.status, expectedStatus);
    assert.equal(candidate.code, expectedCode);
    return;
  }
  assert.fail(`expected_${expectedCode}`);
}

function assertOnlyIds(rows: Row[], key: string, expectedIds: string[]) {
  assert.deepEqual(
    rows.map((row) => String(row[key])).sort(),
    [...expectedIds].sort(),
  );
}

function assertRunProjection(rows: Row[]) {
  for (const row of rows) {
    assert.equal("input_summary" in row, false);
    assert.equal("output_summary" in row, false);
    assert.equal("error_message" in row, false);
  }
}

async function createBaseSchema(client: Client) {
  await client.query(`
    CREATE TABLE users(
      user_id TEXT PRIMARY KEY,
      name TEXT NOT NULL
    );
    CREATE TABLE agents(
      agent_id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      status TEXT NOT NULL
    );
    CREATE TABLE tasks(
      task_id TEXT PRIMARY KEY,
      workspace_id TEXT NOT NULL,
      title TEXT NOT NULL,
      description TEXT,
      status TEXT NOT NULL,
      priority TEXT NOT NULL,
      risk_level TEXT NOT NULL,
      owner_agent_id TEXT,
      acceptance_criteria TEXT,
      budget_limit_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );
    CREATE TABLE runs(
      run_id TEXT PRIMARY KEY,
      workspace_id TEXT NOT NULL,
      task_id TEXT NOT NULL,
      agent_id TEXT NOT NULL,
      runtime_type TEXT NOT NULL,
      status TEXT NOT NULL,
      duration_ms INTEGER,
      input_summary TEXT,
      output_summary TEXT,
      error_message TEXT,
      cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
      started_at TEXT NOT NULL,
      created_at TEXT NOT NULL
    );
    CREATE TABLE tool_calls(
      tool_call_id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL
    );
    CREATE TABLE approvals(
      approval_id TEXT PRIMARY KEY,
      decision TEXT NOT NULL,
      task_id TEXT NOT NULL,
      run_id TEXT NOT NULL,
      tool_call_id TEXT,
      requested_by_agent_id TEXT,
      reason TEXT,
      expires_at TEXT,
      decided_at TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE memories(
      memory_id TEXT PRIMARY KEY,
      workspace_id TEXT NOT NULL,
      review_status TEXT NOT NULL,
      ttl_review_due_at TEXT
    );
    CREATE TABLE evaluations(
      evaluation_id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL
    );
    CREATE TABLE artifacts(
      artifact_id TEXT PRIMARY KEY,
      task_id TEXT,
      run_id TEXT
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
  `);
}

async function applyHumanSessionMigration(client: Client) {
  const baseMigrationBytes = await readFile(BASE_MIGRATION_PATH);
  const upgradeMigrationBytes = await readFile(UPGRADE_MIGRATION_PATH);
  const onlineIndexMigrationBytes = await readFile(ONLINE_INDEX_MIGRATION_PATH);
  const baseMigrationChecksum = createHash("sha256").update(baseMigrationBytes).digest("hex");
  const upgradeMigrationChecksum = createHash("sha256").update(upgradeMigrationBytes).digest("hex");
  const onlineIndexMigrationChecksum = createHash("sha256").update(onlineIndexMigrationBytes).digest("hex");
  assert.equal(baseMigrationChecksum, HUMAN_MEMORY_SCHEMA_V1_CHECKSUM, "base_migration_checksum_fixture_mismatch");
  assert.equal(upgradeMigrationChecksum, HUMAN_MEMORY_SCHEMA_CHECKSUM, "upgrade_migration_checksum_fixture_mismatch");
  assert.equal(
    onlineIndexMigrationChecksum,
    HUMAN_MEMORY_SCHEMA_ONLINE_INDEX_CHECKSUM,
    "online_index_migration_checksum_fixture_mismatch",
  );
  await client.query(baseMigrationBytes.toString("utf8"));
  await client.query(upgradeMigrationBytes.toString("utf8"));
  await client.query(onlineIndexMigrationBytes.toString("utf8"));
  await client.query(
    `INSERT INTO agentops_schema_migrations(
      component,version,schema_contract,checksum,applied_at
    ) VALUES($1,$2,$3,$4,$5)`,
    [
      HUMAN_MEMORY_SCHEMA_COMPONENT,
      HUMAN_MEMORY_SCHEMA_VERSION,
      HUMAN_MEMORY_SCHEMA_CONTRACT,
      HUMAN_MEMORY_SCHEMA_CHECKSUM,
      new Date().toISOString(),
    ],
  );

  const column = await client.query<{ is_nullable: string }>(
    `SELECT is_nullable FROM information_schema.columns
    WHERE table_schema=current_schema() AND table_name='audit_logs' AND column_name='workspace_id'`,
  );
  assert.equal(column.rows[0]?.is_nullable, "YES");
  const index = await client.query<{ indexname: string }>(
    `SELECT indexname FROM pg_indexes
    WHERE schemaname=current_schema() AND indexname='idx_audit_logs_workspace_created'`,
  );
  assert.equal(index.rows[0]?.indexname, "idx_audit_logs_workspace_created");
}

async function seed(client: Client) {
  const now = new Date();
  const nowText = now.toISOString();
  const futureText = new Date(now.getTime() + 60 * 60 * 1000).toISOString();
  const pastText = new Date(now.getTime() - 60 * 60 * 1000).toISOString();

  await client.query(
    `INSERT INTO users(user_id,name) VALUES
      ($1,'Single Workspace User'),
      ($2,'Multiple Workspace User')`,
    [USER_SINGLE, USER_MULTI],
  );
  await client.query(
    `INSERT INTO workspace_memberships(workspace_id,user_id,role,status,created_at,updated_at) VALUES
      ($1,$3,'viewer','active',$5,$5),
      ($1,$4,'operator','active',$5,$5),
      ($2,$4,'viewer','active',$5,$5)`,
    [WORKSPACE_A, WORKSPACE_B, USER_SINGLE, USER_MULTI, nowText],
  );
  await client.query(
    `INSERT INTO human_sessions(
      session_id,user_id,session_hash,status,created_at,expires_at,last_seen_at,revoked_at
    ) VALUES
      ('hss_read_single',$1,$3,'active',$5,$6,NULL,NULL),
      ('hss_read_multi',$2,$4,'active',$5,$6,NULL,NULL)`,
    [
      USER_SINGLE,
      USER_MULTI,
      sessionHash(SESSION_TOKEN_SINGLE),
      sessionHash(SESSION_TOKEN_MULTI),
      nowText,
      futureText,
    ],
  );

  const agentsA = [AGENT_OWNER_A, AGENT_TOKEN_A, AGENT_SESSION_A, AGENT_REVOKED_A, ...RUN_AGENTS_A];
  const agentsB = ["agt_read_owner_b", "agt_read_token_b", "agt_read_session_b", "agt_read_run_b"];
  for (const agentId of [...agentsA, ...agentsB]) {
    await client.query(
      "INSERT INTO agents(agent_id,name,status) VALUES($1,$2,'running')",
      [agentId, `Contract ${agentId}`],
    );
  }

  await client.query(
    `INSERT INTO tasks(
      task_id,workspace_id,title,description,status,priority,risk_level,owner_agent_id,
      acceptance_criteria,budget_limit_usd,created_at,updated_at
    )
    SELECT
      'tsk_a_' || lpad(value::text,3,'0'),$1,'Workspace A task ' || value,
      'tenant A only',
      CASE value WHEN 1 THEN 'completed' WHEN 2 THEN 'failed' WHEN 3 THEN 'blocked' ELSE 'queued' END,
      'medium','low',$2,'contract acceptance',10,
      (TIMESTAMPTZ '2026-07-19T00:00:00Z' + value * INTERVAL '1 minute')::TEXT,
      (TIMESTAMPTZ '2026-07-19T00:00:00Z' + value * INTERVAL '1 minute')::TEXT
    FROM generate_series(1,205) AS value`,
    [WORKSPACE_A, AGENT_OWNER_A],
  );
  await client.query(
    `INSERT INTO tasks(
      task_id,workspace_id,title,description,status,priority,risk_level,owner_agent_id,
      acceptance_criteria,budget_limit_usd,created_at,updated_at
    )
    SELECT
      'tsk_b_' || lpad(value::text,3,'0'),$1,'Workspace B task ' || value,
      'tenant B only','failed','high','high',$2,'other tenant',999,
      (TIMESTAMPTZ '2026-07-20T00:00:00Z' + value * INTERVAL '1 minute')::TEXT,
      (TIMESTAMPTZ '2026-07-20T00:00:00Z' + value * INTERVAL '1 minute')::TEXT
    FROM generate_series(1,3) AS value`,
    [WORKSPACE_B, agentsB[0]],
  );

  for (let value = 1; value <= 23; value += 1) {
    const runAgent = RUN_AGENTS_A[(value - 1) % RUN_AGENTS_A.length];
    const taskId = value <= 3 ? "tsk_a_001" : "tsk_a_002";
    const createdAt = new Date(Date.UTC(2026, 6, 19, 0, value)).toISOString();
    const startedAt = new Date(Date.UTC(2026, 6, 19, 2, 60 - value)).toISOString();
    await client.query(
      `INSERT INTO runs(
        run_id,workspace_id,task_id,agent_id,runtime_type,status,duration_ms,
        input_summary,output_summary,error_message,cost_usd,started_at,created_at
      ) VALUES($1,$2,$3,$4,'contract-runtime',$5,$6,$7,$8,$9,$10,$11,$12)`,
      [
        `run_a_${String(value).padStart(2, "0")}`,
        WORKSPACE_A,
        taskId,
        runAgent,
        value === 2 ? "failed" : "completed",
        value * 10,
        `sensitive input ${value}`,
        `sensitive output ${value}`,
        value === 2 ? "sensitive failure" : null,
        value,
        startedAt,
        createdAt,
      ],
    );
  }
  await client.query(
    `INSERT INTO runs(
      run_id,workspace_id,task_id,agent_id,runtime_type,status,duration_ms,input_summary,
      output_summary,error_message,cost_usd,started_at,created_at
    ) VALUES(
      'run_b_01',$1,'tsk_b_001',$2,'other-runtime','failed',1,
      'other tenant input','other tenant output','other tenant failure',999,$3,$3
    )`,
    [WORKSPACE_B, agentsB[3], "2026-07-21T00:00:00.000Z"],
  );
  await client.query(
    `INSERT INTO runs(
      run_id,workspace_id,task_id,agent_id,runtime_type,status,duration_ms,input_summary,
      output_summary,error_message,cost_usd,started_at,created_at
    ) VALUES(
      'run_b_shared_running',$1,'tsk_b_002',$2,'other-runtime','running',NULL,
      'other tenant shared input',NULL,NULL,0,$3,$3
    )`,
    [WORKSPACE_B, AGENT_OWNER_A, "2026-07-22T00:00:00.000Z"],
  );

  await client.query(
    `INSERT INTO tool_calls(tool_call_id,run_id) VALUES
      ('tool_a_01','run_a_01'),('tool_b_01','run_b_01')`,
  );
  await client.query(
    `INSERT INTO approvals(
      approval_id,decision,task_id,run_id,tool_call_id,requested_by_agent_id,
      reason,expires_at,decided_at,created_at
    ) VALUES
      ('ap_a_01','pending','tsk_a_001','run_a_01','tool_a_01',$1,'A approval',$3,NULL,$2),
      ('ap_b_01','pending','tsk_b_001','run_b_01','tool_b_01',$4,'B approval',$3,NULL,$2),
      ('ap_a_cross_tool','pending','tsk_a_001','run_a_01','tool_b_01',$1,'Invalid cross-run tool',$3,NULL,$2)`,
    [AGENT_OWNER_A, nowText, futureText, agentsB[0]],
  );
  await client.query(
    `INSERT INTO memories(memory_id,workspace_id,review_status,ttl_review_due_at) VALUES
      ('mem_a_stale',$1,'stale',NULL),
      ('mem_a_due',$1,'approved',$2),
      ('mem_a_fresh',$1,'approved',$3),
      ('mem_b_stale',$4,'stale',$2)`,
    [WORKSPACE_A, pastText, futureText, WORKSPACE_B],
  );
  await client.query(
    `INSERT INTO evaluations(evaluation_id,run_id) VALUES
      ('eval_a_01','run_a_01'),('eval_b_01','run_b_01')`,
  );
  await client.query(
    `INSERT INTO artifacts(artifact_id,task_id,run_id) VALUES
      ('artifact_a_01','tsk_a_001','run_a_01'),
      ('artifact_b_01','tsk_b_001','run_b_01')`,
  );

  await client.query(
    `INSERT INTO agent_gateway_tokens(
      token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,
      created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at
    ) VALUES
      ('tok_read_a',$1,$2,$3,'[]','active','contract',300,$6,$7,NULL,NULL,NULL),
      ('tok_read_b',$4,$5,$8,'[]','active','contract',300,$6,$7,NULL,NULL,NULL),
      ('tok_read_revoked','e' || repeat('0',63),$2,$9,'[]','revoked','contract',300,$6,$7,$6,NULL,NULL)`,
    [
      "a".repeat(64),
      WORKSPACE_A,
      AGENT_TOKEN_A,
      "b".repeat(64),
      WORKSPACE_B,
      nowText,
      futureText,
      agentsB[1],
      AGENT_REVOKED_A,
    ],
  );
  await client.query(
    `INSERT INTO agent_gateway_sessions(
      session_id,session_hash,parent_token_id,workspace_id,agent_id,scopes_json,status,
      created_at,expires_at,revoked_at,last_used_at
    ) VALUES
      ('ags_read_a',$1,NULL,$2,$3,'[]','active',$6,$7,NULL,NULL),
      ('ags_read_b',$4,NULL,$5,$8,'[]','active',$6,$7,NULL,NULL)`,
    [
      "c".repeat(64),
      WORKSPACE_A,
      AGENT_SESSION_A,
      "d".repeat(64),
      WORKSPACE_B,
      nowText,
      futureText,
      agentsB[2],
    ],
  );

  const auditRows: Array<[string, string, string, string]> = [
    ["aud_a_task", WORKSPACE_A, "tasks", "tsk_a_001"],
    ["aud_a_run", WORKSPACE_A, "runs", "run_a_01"],
    ["aud_a_approval", WORKSPACE_A, "approvals", "ap_a_01"],
    ["aud_a_memory", WORKSPACE_A, "memories", "mem_a_stale"],
    ["aud_a_tool", WORKSPACE_A, "tool_calls", "tool_a_01"],
    ["aud_a_evaluation", WORKSPACE_A, "evaluations", "eval_a_01"],
    ["aud_a_artifact", WORKSPACE_A, "artifacts", "artifact_a_01"],
    ["aud_b_task", WORKSPACE_B, "tasks", "tsk_b_001"],
    ["aud_b_structured_points_a", WORKSPACE_B, "tasks", "tsk_a_001"],
  ];
  for (const [auditId, workspaceId, entityType, entityId] of auditRows) {
    await client.query(
      `INSERT INTO audit_logs(
        audit_id,workspace_id,actor_type,actor_id,action,entity_type,entity_id,
        before_hash,after_hash,metadata_json,tamper_chain_hash,created_at
      ) VALUES($1,$2,'user','usr-contract','read.contract',$3,$4,$5,$6,$7,$8,$9)`,
      [
        auditId,
        workspaceId,
        entityType,
        entityId,
        `before-${auditId}`,
        `after-${auditId}`,
        JSON.stringify({ secret: `metadata-${auditId}`, workspace_id: workspaceId }),
        `chain-${auditId}`,
        nowText,
      ],
    );
  }
  await client.query(
    `INSERT INTO audit_logs(
      audit_id,workspace_id,actor_type,actor_id,action,entity_type,entity_id,
      before_hash,after_hash,metadata_json,tamper_chain_hash,created_at
    ) VALUES(
      'aud_unbound',NULL,'system',NULL,'legacy.unbound','tasks','tsk_a_001',
      'before-unbound','after-unbound','{"secret":true}','chain-unbound',$1
    )`,
    [nowText],
  );
}

async function verifyAuditWorkspaceBinding(client: Client) {
  await assert.rejects(
    client.query(
      `INSERT INTO audit_logs(
        audit_id,workspace_id,actor_type,actor_id,action,entity_type,entity_id,
        metadata_json,created_at
      ) VALUES(
        'aud_constraint_retag',$1,'user','usr-contract','read.contract','tasks','tsk_a_001',$2,$3
      )`,
      [WORKSPACE_A, JSON.stringify({ workspace_id: WORKSPACE_B }), new Date().toISOString()],
    ),
    (error: unknown) => (error as { code?: string }).code === "23514",
  );

  await client.query(
    "ALTER TABLE audit_logs DROP CONSTRAINT audit_logs_workspace_metadata_match",
  );
  await client.query(
    `INSERT INTO audit_logs(
      audit_id,workspace_id,actor_type,actor_id,action,entity_type,entity_id,
      metadata_json,created_at
    ) VALUES(
      'aud_query_retag',$1,'user','usr-contract','read.contract','tasks','tsk_a_001',$2,$3
    )`,
    [WORKSPACE_A, JSON.stringify({ workspace_id: WORKSPACE_B }), new Date().toISOString()],
  );
  await expectHttpError(
    () => listWorkspaceAudit(humanHeaders(SESSION_TOKEN_SINGLE), undefined, "200"),
    503,
    "human_memory_schema_constraints_mismatch",
  );
}

async function verifyAuthentication(client: PoolClient) {
  const automatic = await authenticateHumanMember(
    client,
    humanHeaders(SESSION_TOKEN_SINGLE),
    undefined,
  );
  assert.equal(automatic.workspaceId, WORKSPACE_A);
  assert.equal(automatic.userId, USER_SINGLE);

  const explicitQuery = await authenticateHumanMember(
    client,
    humanHeaders(SESSION_TOKEN_MULTI),
    WORKSPACE_B,
  );
  assert.equal(explicitQuery.workspaceId, WORKSPACE_B);

  const explicitHeader = await authenticateHumanMember(
    client,
    humanHeaders(SESSION_TOKEN_MULTI, WORKSPACE_A),
    undefined,
  );
  assert.equal(explicitHeader.workspaceId, WORKSPACE_A);

  await expectHttpError(
    () => authenticateHumanMember(client, humanHeaders(SESSION_TOKEN_MULTI), undefined),
    403,
    "workspace_id_required",
  );
  await expectHttpError(
    () => authenticateHumanMember(client, humanHeaders(SESSION_TOKEN_MULTI, WORKSPACE_B), WORKSPACE_A),
    403,
    "forbidden",
  );
}

async function verifyReadModels() {
  const headersA = humanHeaders(SESSION_TOKEN_SINGLE);
  const headersMulti = humanHeaders(SESSION_TOKEN_MULTI);
  const runList = listWorkspaceRuns as unknown as RunList;

  const cappedTasks = await listWorkspaceTasks(headersA, undefined, "200");
  assert.equal(cappedTasks.status, 200);
  assert.equal(cappedTasks.body.length, 200);
  assert.ok(cappedTasks.body.every((row) => row.task_id.startsWith("tsk_a_")));
  await expectHttpError(() => listWorkspaceTasks(headersA, undefined, "201"), 400, "limit_invalid");
  await expectHttpError(() => listWorkspaceTasks(headersA, undefined, "0"), 400, "limit_invalid");
  await expectHttpError(() => runList(headersA, undefined, "invalid"), 400, "limit_invalid");
  await expectHttpError(
    () => runList(headersA, undefined, "20", { taskId: "invalid task id" }),
    400,
    "task_id_invalid",
  );

  const tasksB = await listWorkspaceTasks(headersMulti, WORKSPACE_B, "20");
  assertOnlyIds(tasksB.body, "task_id", ["tsk_b_001", "tsk_b_002", "tsk_b_003"]);

  const runsA = await runList(headersA, undefined, "200");
  assert.equal(runsA.body.length, 23);
  assert.equal(runsA.body[0]?.run_id, "run_a_23");
  assert.equal(runsA.body[22]?.run_id, "run_a_01");
  assertRunProjection(runsA.body);

  const taskRuns = await runList(headersA, undefined, "200", { taskId: "tsk_a_001" });
  assertOnlyIds(taskRuns.body, "run_id", ["run_a_01", "run_a_02", "run_a_03"]);
  assert.ok(taskRuns.body.every((row) => row.task_id === "tsk_a_001"));

  const agentRuns = await runList(headersA, undefined, "200", { agentId: RUN_AGENTS_A[0] });
  assert.ok(agentRuns.body.length > 0);
  assert.ok(agentRuns.body.every((row) => row.agent_id === RUN_AGENTS_A[0]));

  const crossTenantFilter = await runList(headersA, undefined, "200", { taskId: "tsk_b_001" });
  assert.deepEqual(crossTenantFilter.body, []);
  const runsB = await runList(headersMulti, WORKSPACE_B, "20");
  assertOnlyIds(runsB.body, "run_id", ["run_b_01", "run_b_shared_running"]);
  assertRunProjection(runsB.body);

  const approvalsA = await listWorkspaceApprovals(headersA, undefined, "20");
  assertOnlyIds(approvalsA.body, "approval_id", ["ap_a_01"]);
  const approvalsB = await listWorkspaceApprovals(headersMulti, WORKSPACE_B, "20");
  assertOnlyIds(approvalsB.body, "approval_id", ["ap_b_01"]);

  const auditA = await listWorkspaceAudit(headersA, undefined, "120");
  assertOnlyIds(auditA.body, "audit_id", [
    "aud_a_task",
    "aud_a_run",
    "aud_a_approval",
    "aud_a_memory",
    "aud_a_tool",
    "aud_a_evaluation",
    "aud_a_artifact",
  ]);
  for (const row of auditA.body) {
    for (const forbidden of [
      "workspace_id",
      "metadata_json",
      "before_hash",
      "after_hash",
      "tamper_chain_hash",
    ]) {
      assert.equal(forbidden in row, false, `audit_projection_leaked_${forbidden}`);
    }
  }
  const auditB = await listWorkspaceAudit(headersMulti, WORKSPACE_B, "120");
  assertOnlyIds(auditB.body, "audit_id", ["aud_b_task", "aud_b_structured_points_a"]);

  const metrics = await workspaceDashboardMetrics(headersA, undefined);
  assert.equal(metrics.status, 200);
  assert.equal(metrics.body.agents_total, 10);
  assert.equal(metrics.body.agents_running, 0);
  assert.equal(metrics.body.tasks_completed_total, 1);
  assert.equal(metrics.body.pending_approvals, 1);
  assert.equal(metrics.body.stale_or_due_memories, 2);
  assert.ok(Math.abs(Number(metrics.body.failure_rate) - (2 / 205)) < 1e-12);
  assert.equal(metrics.body.total_cost_usd, 276);

  const metricsB = await workspaceDashboardMetrics(headersMulti, WORKSPACE_B);
  assert.equal(metricsB.status, 200);
  assert.equal(metricsB.body.agents_running, 1);

  const recentRuns = metrics.body.recent_runs as Row[];
  assert.equal(recentRuns.length, 20);
  assert.equal(recentRuns[0]?.run_id, "run_a_23");
  assert.equal(recentRuns[19]?.run_id, "run_a_04");
  assertRunProjection(recentRuns);

  const topCostAgents = metrics.body.top_cost_agents as Row[];
  assert.equal(topCostAgents.length, 5);
  assert.ok(topCostAgents.every((row) => String(row.agent_id).startsWith("agt_read_run_a_")));
  assert.equal("runtime_health" in (metrics.body as Row), false);

  const statusDistribution = metrics.body.task_status_distribution as Row[];
  assert.deepEqual(statusDistribution, [
    { status: "blocked", count: 1 },
    { status: "completed", count: 1 },
    { status: "failed", count: 1 },
    { status: "queued", count: 202 },
  ]);
}

function routeRequest(path: string, token: string, workspaceHeader?: string) {
  const headers = humanHeaders(token, workspaceHeader);
  return new NextRequest(`http://127.0.0.1${path}`, { method: "GET", headers });
}

async function assertPrivateRouteResponse(response: Response) {
  assert.equal(response.status, 200);
  assert.match(String(response.headers.get("cache-control") || ""), /no-store/i);
  const vary = String(response.headers.get("vary") || "").toLowerCase();
  assert.ok(vary.includes("cookie"));
  assert.ok(vary.includes("x-agentops-workspace-id"));
  return response.json() as Promise<unknown>;
}

async function verifyHttpRoutes() {
  const tasks = await assertPrivateRouteResponse(await getTasksRoute(routeRequest(
    `/api/mis/tasks?workspace_id=${WORKSPACE_B}&limit=2`,
    SESSION_TOKEN_MULTI,
  )));
  assert.ok(Array.isArray(tasks));
  assert.equal(tasks.length, 2);
  assert.ok(tasks.every((row) => String((row as Row).task_id).startsWith("tsk_b_")));

  const runs = await assertPrivateRouteResponse(await getRunsRoute(routeRequest(
    "/api/mis/runs?task_id=tsk_a_001&limit=2",
    SESSION_TOKEN_SINGLE,
  )));
  assert.ok(Array.isArray(runs));
  assert.equal(runs.length, 2);
  assertRunProjection(runs as Row[]);

  const approvals = await assertPrivateRouteResponse(await getApprovalsRoute(routeRequest(
    "/api/mis/approvals?limit=20",
    SESSION_TOKEN_SINGLE,
  )));
  assert.ok(Array.isArray(approvals));
  assert.equal(approvals.length, 1);

  const audit = await assertPrivateRouteResponse(await getAuditRoute(routeRequest(
    "/api/mis/audit?limit=20",
    SESSION_TOKEN_SINGLE,
  )));
  assert.ok(Array.isArray(audit));
  assert.equal(audit.length, 7);

  const metrics = await assertPrivateRouteResponse(await getDashboardMetricsRoute(routeRequest(
    "/api/mis/dashboard/metrics",
    SESSION_TOKEN_SINGLE,
  ))) as Row;
  assert.equal(metrics.pending_approvals, 1);
  assert.equal(metrics.agents_total, 10);
  assert.equal(metrics.agents_running, 0);

  const metricsB = await assertPrivateRouteResponse(await getDashboardMetricsRoute(routeRequest(
    `/api/mis/dashboard/metrics?workspace_id=${WORKSPACE_B}`,
    SESSION_TOKEN_MULTI,
  ))) as Row;
  assert.equal(metricsB.agents_running, 1);

  const mismatch = await getTasksRoute(routeRequest(
    `/api/mis/tasks?workspace_id=${WORKSPACE_A}`,
    SESSION_TOKEN_MULTI,
    WORKSPACE_B,
  ));
  assert.equal(mismatch.status, 403);
  assert.equal((await mismatch.json() as Row).error, "forbidden");
}

async function closeControlPlanePool() {
  const globalPool = globalThis as typeof globalThis & {
    __agentOpsControlPlanePool?: Pool;
  };
  const ownedPool = globalPool.__agentOpsControlPlanePool;
  if (ownedPool) {
    await ownedPool.end();
    globalPool.__agentOpsControlPlanePool = undefined;
  }
}

async function main() {
  const baseDsn = String(
    process.env.AGENTOPS_TEST_POSTGRES_DSN || process.env.AGENTOPS_POSTGRES_DSN || "",
  ).trim();
  if (!baseDsn) throw new Error("postgres_dsn_required");

  const schema = `agentops_workspace_read_${randomBytes(8).toString("hex")}`;
  const quotedSchema = `"${schema}"`;
  const admin = new Client({
    connectionString: baseDsn,
    ssl: sslEnabled() ? { rejectUnauthorized: true } : undefined,
    application_name: "agentops-workspace-read-model-contract-setup",
  });
  let schemaCreated = false;

  process.env.AGENTOPS_POSTGRES_DSN = scopedDsn(baseDsn, schema);
  process.env.AGENTOPS_HUMAN_SESSION_HMAC_KEY = SESSION_HMAC_KEY;
  process.env.AGENTOPS_CONTROL_PLANE_MODE = "postgres";
  try {
    await admin.connect();
    await admin.query(`CREATE SCHEMA ${quotedSchema}`);
    schemaCreated = true;
    await admin.query(`SET search_path TO ${quotedSchema}`);
    await createBaseSchema(admin);
    await applyHumanSessionMigration(admin);
    await seed(admin);
    await verifyAuthentication(admin as unknown as PoolClient);
    await verifyReadModels();
    await verifyHttpRoutes();
    await verifyAuditWorkspaceBinding(admin);

    output({
      ok: true,
      contract: "nextjs_postgres_workspace_read_models_v1",
      checks: {
        single_membership_auto_binding: true,
        explicit_workspace_binding: true,
        ambiguous_and_mismatched_workspace_rejected: true,
        workspace_reads_isolated: true,
        audit_uses_chain_bound_workspace_and_omits_sensitive_fields: true,
        audit_workspace_constraint_rejects_retag: true,
        audit_workspace_reads_fail_closed_after_constraint_loss: true,
        strict_limit_and_run_filters: true,
        dashboard_metrics_workspace_scoped: true,
        workspace_running_agents_scoped_to_runs: true,
        gateway_bound_agents_counted: true,
        revoked_gateway_bindings_excluded: true,
        untrusted_runtime_health_omitted: true,
        authenticated_http_routes_return_private_200: true,
      },
      credentials_omitted: true,
    });
  } finally {
    await closeControlPlanePool().catch(() => undefined);
    if (schemaCreated) {
      await admin.query("SET search_path TO public").catch(() => undefined);
      await admin.query(`DROP SCHEMA ${quotedSchema} CASCADE`).catch(() => undefined);
    }
    await admin.end().catch(() => undefined);
  }
}

main().catch((error: unknown) => {
  const candidate = error as { code?: string };
  const code = candidate?.code
    || (error instanceof Error && /^[a-z0-9_]+$/.test(error.message)
      ? error.message
      : "workspace_read_model_contract_failed");
  output({ ok: false, error: code, credentials_omitted: true });
  process.exitCode = 1;
});
