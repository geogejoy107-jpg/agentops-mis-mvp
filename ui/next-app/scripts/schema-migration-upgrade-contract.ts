import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { Client, type PoolClient } from "pg";

import {
  assertHumanMemorySchemaReady,
  HUMAN_MEMORY_SCHEMA_CHECKSUM,
  HUMAN_MEMORY_SCHEMA_COMPONENT,
  HUMAN_MEMORY_SCHEMA_CONTRACT,
  HUMAN_MEMORY_SCHEMA_ONLINE_INDEX_CHECKSUM,
  HUMAN_MEMORY_SCHEMA_VERSION,
  HUMAN_MEMORY_SCHEMA_V1_CHECKSUM,
  HUMAN_MEMORY_SCHEMA_V1_CONTRACT,
  HUMAN_MEMORY_SCHEMA_V1_VERSION,
  HUMAN_MEMORY_SCHEMA_V2_CHECKSUM,
  HUMAN_MEMORY_SCHEMA_V2_CONTRACT,
  HUMAN_MEMORY_SCHEMA_V2_VERSION,
  HUMAN_MEMORY_SCHEMA_V3_CHECKSUM,
  HUMAN_MEMORY_SCHEMA_V3_CONTRACT,
  HUMAN_MEMORY_SCHEMA_V3_VERSION,
} from "../src/server/controlPlane/schemaReadiness";

const NEXT_APP_ROOT = fileURLToPath(new URL("../", import.meta.url));
const TSX_PATH = fileURLToPath(new URL("../node_modules/.bin/tsx", import.meta.url));
const MIGRATOR_PATH = fileURLToPath(new URL("./migrate-postgres.ts", import.meta.url));
const V1_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260718_human_session_memory_review.sql", import.meta.url),
);
const V2_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260719_workspace_read_models_v2.sql", import.meta.url),
);
const ONLINE_INDEX_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260719_workspace_read_models_v2_online_indexes.sql", import.meta.url),
);
const V3_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260719_human_approval_decisions_v3.sql", import.meta.url),
);
const V4_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260719_approval_kind_bindings_v4.sql", import.meta.url),
);

type MigrationResult = {
  exitCode: number | null;
  stdout: string;
  stderr: string;
};

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

function quotedIdentifier(value: string) {
  assert.match(value, /^[a-z][a-z0-9_]+$/);
  return `"${value}"`;
}

function hasPostgresCode(error: unknown, code: string) {
  return error instanceof Error
    && "code" in error
    && (error as Error & { code?: string }).code === code;
}

async function runMigrator(dsn: string): Promise<MigrationResult> {
  return await new Promise((resolve, reject) => {
    const child = spawn(TSX_PATH, [MIGRATOR_PATH], {
      cwd: NEXT_APP_ROOT,
      env: {
        ...process.env,
        AGENTOPS_POSTGRES_DSN: dsn,
        DATABASE_URL: dsn,
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk: string) => {
      stderr += chunk;
    });
    child.once("error", reject);
    child.once("close", (exitCode) => resolve({ exitCode, stdout, stderr }));
  });
}

async function createApprovalBindingParentFixture(client: Client) {
  await client.query(`
    CREATE TABLE users(user_id TEXT PRIMARY KEY);
    CREATE TABLE memories(memory_id TEXT PRIMARY KEY);
    CREATE TABLE tasks(
      task_id TEXT PRIMARY KEY,
      workspace_id TEXT NOT NULL
    );
    CREATE TABLE runs(
      run_id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      workspace_id TEXT NOT NULL,
      agent_id TEXT NOT NULL
    );
    CREATE TABLE tool_calls(
      tool_call_id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL,
      agent_id TEXT NOT NULL
    );
    CREATE TABLE evaluations(
      evaluation_id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      run_id TEXT NOT NULL
    );
    CREATE TABLE artifacts(
      artifact_id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      run_id TEXT
    );
    CREATE TABLE plan_evidence_manifests(
      manifest_id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      run_id TEXT NOT NULL
    );
    CREATE TABLE agent_plans(
      plan_id TEXT PRIMARY KEY,
      task_id TEXT,
      run_id TEXT
    );
    CREATE TABLE approvals(
      approval_id TEXT PRIMARY KEY,
      task_id TEXT NOT NULL,
      run_id TEXT NOT NULL,
      tool_call_id TEXT,
      requested_by_agent_id TEXT,
      reason TEXT
    );
    CREATE TABLE prepared_actions(
      prepared_action_id TEXT PRIMARY KEY,
      workspace_id TEXT NOT NULL,
      task_id TEXT NOT NULL,
      run_id TEXT NOT NULL,
      tool_call_id TEXT NOT NULL,
      approval_id TEXT,
      requested_by_agent_id TEXT
    );
    CREATE TABLE agent_gateway_enrollment_requests(
      request_id TEXT PRIMARY KEY,
      approval_id TEXT NOT NULL,
      task_id TEXT NOT NULL,
      run_id TEXT NOT NULL,
      workspace_id TEXT NOT NULL,
      agent_id TEXT NOT NULL
    );
    CREATE TABLE audit_logs(
      audit_id TEXT PRIMARY KEY,
      entity_type TEXT,
      entity_id TEXT,
      action TEXT,
      metadata_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL
    );

    INSERT INTO tasks(task_id,workspace_id)
    VALUES('task_upgrade_contract','workspace_upgrade_contract');
    INSERT INTO runs(run_id,task_id,workspace_id,agent_id)
    VALUES('run_upgrade_contract','task_upgrade_contract','workspace_upgrade_contract','agent_upgrade_contract');
    INSERT INTO tool_calls(tool_call_id,run_id,agent_id) VALUES
      ('tool_upgrade_contract','run_upgrade_contract','agent_upgrade_contract'),
      ('tool_prepared_upgrade_contract','run_upgrade_contract','agent_upgrade_contract');
    INSERT INTO approvals(
      approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,reason
    ) VALUES
      ('approval_run_upgrade_contract','task_upgrade_contract','run_upgrade_contract',NULL,'agent_upgrade_contract','run review'),
      ('approval_tool_upgrade_contract','task_upgrade_contract','run_upgrade_contract','tool_upgrade_contract','agent_upgrade_contract','tool review'),
      ('approval_prepared_upgrade_contract','task_upgrade_contract','run_upgrade_contract','tool_prepared_upgrade_contract','agent_upgrade_contract','prepared action review'),
      ('approval_enrollment_upgrade_contract','task_upgrade_contract','run_upgrade_contract',NULL,'agent_upgrade_contract','enrollment review'),
      ('approval_delivery_upgrade_contract','task_upgrade_contract','run_upgrade_contract',NULL,'agent_upgrade_contract','delivery review');
    INSERT INTO prepared_actions(
      prepared_action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,requested_by_agent_id
    ) VALUES(
      'prepared_upgrade_contract','workspace_upgrade_contract','task_upgrade_contract',
      'run_upgrade_contract','tool_prepared_upgrade_contract','approval_prepared_upgrade_contract',
      'agent_upgrade_contract'
    );
    INSERT INTO agent_gateway_enrollment_requests(
      request_id,approval_id,task_id,run_id,workspace_id,agent_id
    ) VALUES(
      'enrollment_upgrade_contract','approval_enrollment_upgrade_contract','task_upgrade_contract',
      'run_upgrade_contract','workspace_upgrade_contract','agent_upgrade_contract'
    );
    INSERT INTO audit_logs(audit_id,entity_type,entity_id,action,metadata_json,created_at)
    VALUES
    (
      'audit_delivery_upgrade_contract','approvals','approval_delivery_upgrade_contract',
      'workflow.customer_worker_task.delivery_approval',
      '{"workspace_id":"workspace_upgrade_contract"}','2026-07-19T00:00:00Z'
    ),(
      'audit_run_upgrade_contract','approvals','approval_run_upgrade_contract',
      'agent_gateway.approval_request',
      '{"workspace_id":"workspace_upgrade_contract"}','2026-07-19T00:00:00Z'
    );
  `);
}

async function createV1Fixture(
  client: Client,
  migrationSql: string,
  receiptChecksum: string,
) {
  await createApprovalBindingParentFixture(client);
  await client.query(migrationSql);
  await client.query(
    `INSERT INTO agentops_schema_migrations(
      component,version,schema_contract,checksum,applied_at
    ) VALUES($1,$2,$3,$4,CURRENT_TIMESTAMP::TEXT)`,
    [
      HUMAN_MEMORY_SCHEMA_COMPONENT,
      HUMAN_MEMORY_SCHEMA_V1_VERSION,
      HUMAN_MEMORY_SCHEMA_V1_CONTRACT,
      receiptChecksum,
    ],
  );
}

async function createV2Fixture(client: Client, v1Sql: string, v2Sql: string) {
  await createV1Fixture(client, v1Sql, HUMAN_MEMORY_SCHEMA_V1_CHECKSUM);
  await client.query(v2Sql);
  await client.query(
    `UPDATE agentops_schema_migrations
    SET version=$1,schema_contract=$2,checksum=$3,applied_at=CURRENT_TIMESTAMP::TEXT
    WHERE component=$4`,
    [
      HUMAN_MEMORY_SCHEMA_V2_VERSION,
      HUMAN_MEMORY_SCHEMA_V2_CONTRACT,
      HUMAN_MEMORY_SCHEMA_V2_CHECKSUM,
      HUMAN_MEMORY_SCHEMA_COMPONENT,
    ],
  );
}

async function createV3Fixture(client: Client, v1Sql: string, v2Sql: string, v3Sql: string) {
  await createV2Fixture(client, v1Sql, v2Sql);
  await client.query(v3Sql);
  await client.query(
    `UPDATE agentops_schema_migrations
    SET version=$1,schema_contract=$2,checksum=$3,applied_at=CURRENT_TIMESTAMP::TEXT
    WHERE component=$4`,
    [
      HUMAN_MEMORY_SCHEMA_V3_VERSION,
      HUMAN_MEMORY_SCHEMA_V3_CONTRACT,
      HUMAN_MEMORY_SCHEMA_V3_CHECKSUM,
      HUMAN_MEMORY_SCHEMA_COMPONENT,
    ],
  );
}

async function assertApprovalKindUpgrade(client: Client) {
  const column = await client.query<{
    data_type: string;
    is_nullable: string;
    column_default: string | null;
  }>(
    `SELECT data_type,is_nullable,column_default FROM information_schema.columns
    WHERE table_schema=current_schema()
      AND table_name='approvals' AND column_name='approval_kind'`,
  );
  assert.deepEqual(column.rows, [{
    data_type: "text",
    is_nullable: "NO",
    column_default: null,
  }]);

  const kinds = await client.query<{ approval_id: string; approval_kind: string }>(
    `SELECT approval_id,approval_kind FROM approvals ORDER BY approval_id`,
  );
  assert.deepEqual(kinds.rows, [
    { approval_id: "approval_delivery_upgrade_contract", approval_kind: "customer_delivery" },
    { approval_id: "approval_enrollment_upgrade_contract", approval_kind: "agent_enrollment" },
    { approval_id: "approval_prepared_upgrade_contract", approval_kind: "prepared_action" },
    { approval_id: "approval_run_upgrade_contract", approval_kind: "run_execution" },
    { approval_id: "approval_tool_upgrade_contract", approval_kind: "tool_execution" },
  ]);

  const triggers = await client.query<{
    trigger_name: string;
    deferrable: boolean;
    initially_deferred: boolean;
  }>(
    `SELECT trigger_record.tgname AS trigger_name,
      trigger_record.tgdeferrable AS deferrable,
      trigger_record.tginitdeferred AS initially_deferred
    FROM pg_trigger trigger_record
    JOIN pg_class relation ON relation.oid=trigger_record.tgrelid
    JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
    WHERE namespace.nspname=current_schema()
      AND NOT trigger_record.tgisinternal
      AND trigger_record.tgname=ANY($1::text[])
    ORDER BY trigger_record.tgname`,
    [[
      "approvals_kind_binding_enforced",
      "prepared_actions_kind_binding_enforced",
      "enrollment_requests_kind_binding_enforced",
    ]],
  );
  assert.deepEqual(triggers.rows, [
    {
      trigger_name: "approvals_kind_binding_enforced",
      deferrable: true,
      initially_deferred: true,
    },
    {
      trigger_name: "enrollment_requests_kind_binding_enforced",
      deferrable: true,
      initially_deferred: true,
    },
    {
      trigger_name: "prepared_actions_kind_binding_enforced",
      deferrable: true,
      initially_deferred: true,
    },
  ]);

  const enrollmentIndex = await client.query<{ is_unique: boolean; key_count: number }>(
    `SELECT index_record.indisunique AS is_unique,
      index_record.indnkeyatts::integer AS key_count
    FROM pg_index index_record
    JOIN pg_class index_relation ON index_relation.oid=index_record.indexrelid
    JOIN pg_namespace namespace ON namespace.oid=index_relation.relnamespace
    WHERE namespace.nspname=current_schema()
      AND index_relation.relname='idx_agent_gateway_enrollment_approval_unique'`,
  );
  assert.deepEqual(enrollmentIndex.rows, [{ is_unique: true, key_count: 1 }]);

  await assert.rejects(
    client.query(
      `INSERT INTO approvals(
        approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,reason
      ) VALUES(
        'approval_missing_explicit_kind','task_upgrade_contract','run_upgrade_contract',
        NULL,'agent_upgrade_contract','missing explicit kind'
      )`,
    ),
    (error: unknown) => hasPostgresCode(error, "23502"),
  );
  await assert.rejects(
    client.query(
      `INSERT INTO approvals(
        approval_id,approval_kind,task_id,run_id,tool_call_id,requested_by_agent_id,reason
      ) VALUES(
        'approval_invalid_binding','run_execution','missing_task','missing_run',
        NULL,'agent_upgrade_contract','invalid binding'
      )`,
    ),
    (error: unknown) => hasPostgresCode(error, "23514"),
  );
  await assert.rejects(
    client.query(
      `INSERT INTO agent_gateway_enrollment_requests(
        request_id,approval_id,task_id,run_id,workspace_id,agent_id
      ) VALUES(
        'enrollment_duplicate_upgrade_contract','approval_enrollment_upgrade_contract',
        'task_upgrade_contract','run_upgrade_contract','workspace_upgrade_contract',
        'agent_upgrade_contract'
      )`,
    ),
    (error: unknown) => hasPostgresCode(error, "23505"),
  );
  await assert.rejects(
    client.query(
      `WITH inserted_task AS (
        INSERT INTO tasks(task_id,workspace_id)
        VALUES('task_upgrade_rebind','workspace_upgrade_rebind')
        RETURNING task_id
      ), inserted_run AS (
        INSERT INTO runs(run_id,task_id,workspace_id,agent_id)
        SELECT 'run_upgrade_rebind',task_id,'workspace_upgrade_rebind','agent_upgrade_rebind'
        FROM inserted_task
        RETURNING run_id
      )
      UPDATE approvals SET
        task_id=(SELECT task_id FROM inserted_task),
        run_id=(SELECT run_id FROM inserted_run),
        requested_by_agent_id='agent_upgrade_rebind'
      WHERE approval_id='approval_run_upgrade_contract'`,
    ),
    (error: unknown) => hasPostgresCode(error, "23514"),
  );
}

async function assertWorkspaceAuditUpgrade(client: Client) {
  const receipt = await client.query<{
    version: string;
    schema_contract: string;
    checksum: string;
  }>(
    `SELECT version,schema_contract,checksum
    FROM agentops_schema_migrations WHERE component=$1`,
    [HUMAN_MEMORY_SCHEMA_COMPONENT],
  );
  assert.deepEqual(receipt.rows, [{
    version: HUMAN_MEMORY_SCHEMA_VERSION,
    schema_contract: HUMAN_MEMORY_SCHEMA_CONTRACT,
    checksum: HUMAN_MEMORY_SCHEMA_CHECKSUM,
  }]);

  const column = await client.query<{ data_type: string; is_nullable: string }>(
    `SELECT data_type,is_nullable FROM information_schema.columns
    WHERE table_schema=current_schema()
      AND table_name='audit_logs' AND column_name='workspace_id'`,
  );
  assert.deepEqual(column.rows, [{ data_type: "text", is_nullable: "YES" }]);

  const index = await client.query<{ indexdef: string }>(
    `SELECT indexdef FROM pg_indexes
    WHERE schemaname=current_schema()
      AND tablename='audit_logs'
      AND indexname='idx_audit_logs_workspace_created'`,
  );
  assert.equal(index.rows.length, 1);
  assert.match(index.rows[0].indexdef, /\(workspace_id, created_at DESC, audit_id DESC\)$/);

  const constraint = await client.query<{ convalidated: boolean }>(
    `SELECT constraint_record.convalidated
    FROM pg_constraint constraint_record
    JOIN pg_class relation ON relation.oid=constraint_record.conrelid
    JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
    WHERE namespace.nspname=current_schema()
      AND relation.relname='audit_logs'
      AND constraint_record.conname='audit_logs_workspace_metadata_match'`,
  );
  assert.deepEqual(constraint.rows, [{ convalidated: true }]);

  await assertApprovalKindUpgrade(client);
  await assertHumanMemorySchemaReady(client as unknown as PoolClient);
}

async function assertNoWorkspaceAuditUpgrade(client: Client, tamperedChecksum: string) {
  const column = await client.query<{ count: string }>(
    `SELECT COUNT(*)::TEXT AS count FROM information_schema.columns
    WHERE table_schema=current_schema()
      AND table_name='audit_logs' AND column_name='workspace_id'`,
  );
  assert.equal(column.rows[0]?.count, "0");

  const approvalKindColumn = await client.query<{ count: string }>(
    `SELECT COUNT(*)::TEXT AS count FROM information_schema.columns
    WHERE table_schema=current_schema()
      AND table_name='approvals' AND column_name='approval_kind'`,
  );
  assert.equal(approvalKindColumn.rows[0]?.count, "0");

  const receipt = await client.query<{ checksum: string }>(
    `SELECT checksum FROM agentops_schema_migrations WHERE component=$1`,
    [HUMAN_MEMORY_SCHEMA_COMPONENT],
  );
  assert.deepEqual(receipt.rows, [{ checksum: tamperedChecksum }]);
}

async function main() {
  const dsn = String(
    process.env.AGENTOPS_TEST_POSTGRES_DSN || process.env.AGENTOPS_POSTGRES_DSN || "",
  ).trim();
  if (!dsn) throw new Error("postgres_dsn_required");

  const migrationBytes = await readFile(V1_MIGRATION_PATH);
  const migrationChecksum = createHash("sha256").update(migrationBytes).digest("hex");
  assert.equal(migrationChecksum, HUMAN_MEMORY_SCHEMA_V1_CHECKSUM);
  const v2MigrationBytes = await readFile(V2_MIGRATION_PATH);
  const v2MigrationChecksum = createHash("sha256").update(v2MigrationBytes).digest("hex");
  assert.equal(v2MigrationChecksum, HUMAN_MEMORY_SCHEMA_V2_CHECKSUM);
  const onlineIndexMigrationBytes = await readFile(ONLINE_INDEX_MIGRATION_PATH);
  const onlineIndexMigrationChecksum = createHash("sha256").update(onlineIndexMigrationBytes).digest("hex");
  assert.equal(onlineIndexMigrationChecksum, HUMAN_MEMORY_SCHEMA_ONLINE_INDEX_CHECKSUM);
  const v3MigrationBytes = await readFile(V3_MIGRATION_PATH);
  const v3MigrationChecksum = createHash("sha256").update(v3MigrationBytes).digest("hex");
  assert.equal(v3MigrationChecksum, HUMAN_MEMORY_SCHEMA_V3_CHECKSUM);
  const v4MigrationBytes = await readFile(V4_MIGRATION_PATH);
  const v4MigrationChecksum = createHash("sha256").update(v4MigrationBytes).digest("hex");
  assert.equal(v4MigrationChecksum, HUMAN_MEMORY_SCHEMA_CHECKSUM);
  assert.match(v2MigrationBytes.toString("utf8"), /SET LOCAL lock_timeout = '5s'/);
  assert.doesNotMatch(v2MigrationBytes.toString("utf8"), /CREATE INDEX/);
  assert.match(onlineIndexMigrationBytes.toString("utf8"), /CREATE INDEX CONCURRENTLY/);
  assert.match(v3MigrationBytes.toString("utf8"), /human_approval_decision_requests/);
  assert.match(v4MigrationBytes.toString("utf8"), /ALTER COLUMN approval_kind DROP DEFAULT/);
  assert.match(v4MigrationBytes.toString("utf8"), /'customer_delivery'/);
  assert.match(v4MigrationBytes.toString("utf8"), /DEFERRABLE INITIALLY DEFERRED/);
  assert.match(v4MigrationBytes.toString("utf8"), /idx_agent_gateway_enrollment_approval_unique/);
  const migrationSql = migrationBytes.toString("utf8");
  const legalSchema = `agentops_schema_upgrade_${randomBytes(8).toString("hex")}`;
  const v2Schema = `agentops_schema_upgrade_v2_${randomBytes(8).toString("hex")}`;
  const v3Schema = `agentops_schema_upgrade_v3_${randomBytes(8).toString("hex")}`;
  const unclassifiedSchema = `agentops_schema_upgrade_unclassified_${randomBytes(8).toString("hex")}`;
  const prefilledKindSchema = `agentops_schema_upgrade_prefilled_kind_${randomBytes(8).toString("hex")}`;
  const driftSchema = `agentops_schema_drift_${randomBytes(8).toString("hex")}`;
  const schemasCreated: string[] = [];
  const clients: Client[] = [];
  const connectionOptions = {
    ssl: sslEnabled() ? { rejectUnauthorized: true } : undefined,
  };
  const admin = new Client({
    connectionString: dsn,
    ...connectionOptions,
    application_name: "agentops-mis-schema-upgrade-contract-admin",
  });

  try {
    await admin.connect();
    for (const schema of [
      legalSchema,
      v2Schema,
      v3Schema,
      unclassifiedSchema,
      prefilledKindSchema,
      driftSchema,
    ]) {
      await admin.query(`CREATE SCHEMA ${quotedIdentifier(schema)}`);
      schemasCreated.push(schema);
    }

    const legalDsn = scopedDsn(dsn, legalSchema);
    const legalClient = new Client({
      connectionString: legalDsn,
      ...connectionOptions,
      application_name: "agentops-mis-schema-upgrade-contract-legal",
    });
    clients.push(legalClient);
    await legalClient.connect();
    await createV1Fixture(legalClient, migrationSql, HUMAN_MEMORY_SCHEMA_V1_CHECKSUM);
    const legalMigration = await runMigrator(legalDsn);
    assert.equal(
      legalMigration.exitCode,
      0,
      `legal_v1_upgrade_failed:${legalMigration.stdout.trim()}:${legalMigration.stderr.trim()}`,
    );
    assert.match(legalMigration.stdout, /"ready":true/);
    await assertWorkspaceAuditUpgrade(legalClient);

    const v2Dsn = scopedDsn(dsn, v2Schema);
    const v2Client = new Client({
      connectionString: v2Dsn,
      ...connectionOptions,
      application_name: "agentops-mis-schema-upgrade-contract-v2",
    });
    clients.push(v2Client);
    await v2Client.connect();
    await createV2Fixture(v2Client, migrationSql, v2MigrationBytes.toString("utf8"));
    const v2Migration = await runMigrator(v2Dsn);
    assert.equal(
      v2Migration.exitCode,
      0,
      `legal_v2_upgrade_failed:${v2Migration.stdout.trim()}:${v2Migration.stderr.trim()}`,
    );
    await assertWorkspaceAuditUpgrade(v2Client);

    const v3Dsn = scopedDsn(dsn, v3Schema);
    const v3Client = new Client({
      connectionString: v3Dsn,
      ...connectionOptions,
      application_name: "agentops-mis-schema-upgrade-contract-v3",
    });
    clients.push(v3Client);
    await v3Client.connect();
    await createV3Fixture(
      v3Client,
      migrationSql,
      v2MigrationBytes.toString("utf8"),
      v3MigrationBytes.toString("utf8"),
    );
    const v3Migration = await runMigrator(v3Dsn);
    assert.equal(
      v3Migration.exitCode,
      0,
      `legal_v3_upgrade_failed:${v3Migration.stdout.trim()}:${v3Migration.stderr.trim()}`,
    );
    await assertWorkspaceAuditUpgrade(v3Client);

    const unclassifiedDsn = scopedDsn(dsn, unclassifiedSchema);
    const unclassifiedClient = new Client({
      connectionString: unclassifiedDsn,
      ...connectionOptions,
      application_name: "agentops-mis-schema-upgrade-contract-unclassified",
    });
    clients.push(unclassifiedClient);
    await unclassifiedClient.connect();
    await createV1Fixture(unclassifiedClient, migrationSql, HUMAN_MEMORY_SCHEMA_V1_CHECKSUM);
    await unclassifiedClient.query("DELETE FROM audit_logs WHERE audit_id='audit_run_upgrade_contract'");
    const unclassifiedMigration = await runMigrator(unclassifiedDsn);
    assert.notEqual(unclassifiedMigration.exitCode, 0);
    assert.match(
      `${unclassifiedMigration.stdout}\n${unclassifiedMigration.stderr}`,
      /"error":"approval_kind_backfill_evidence_missing"/,
    );
    const unclassifiedColumn = await unclassifiedClient.query<{ count: string }>(
      `SELECT COUNT(*)::TEXT AS count FROM information_schema.columns
      WHERE table_schema=current_schema()
        AND table_name='approvals' AND column_name='approval_kind'`,
    );
    assert.equal(unclassifiedColumn.rows[0]?.count, "0");

    const prefilledKindDsn = scopedDsn(dsn, prefilledKindSchema);
    const prefilledKindClient = new Client({
      connectionString: prefilledKindDsn,
      ...connectionOptions,
      application_name: "agentops-mis-schema-upgrade-contract-prefilled-kind",
    });
    clients.push(prefilledKindClient);
    await prefilledKindClient.connect();
    await createV1Fixture(prefilledKindClient, migrationSql, HUMAN_MEMORY_SCHEMA_V1_CHECKSUM);
    await prefilledKindClient.query("ALTER TABLE approvals ADD COLUMN approval_kind TEXT");
    await prefilledKindClient.query(
      "UPDATE approvals SET approval_kind='customer_delivery' WHERE approval_id='approval_run_upgrade_contract'",
    );
    const prefilledKindMigration = await runMigrator(prefilledKindDsn);
    assert.notEqual(prefilledKindMigration.exitCode, 0);
    assert.match(
      `${prefilledKindMigration.stdout}\n${prefilledKindMigration.stderr}`,
      /"error":"approval_kind_prefill_evidence_mismatch"/,
    );
    const prefilledKindReceipt = await prefilledKindClient.query<{ version: string }>(
      `SELECT version FROM agentops_schema_migrations WHERE component=$1`,
      [HUMAN_MEMORY_SCHEMA_COMPONENT],
    );
    assert.deepEqual(prefilledKindReceipt.rows, [{ version: HUMAN_MEMORY_SCHEMA_V1_VERSION }]);

    await legalClient.query("DROP INDEX idx_audit_logs_workspace_created");
    const resumedOnlineIndexMigration = await runMigrator(legalDsn);
    assert.equal(
      resumedOnlineIndexMigration.exitCode,
      0,
      `online_index_resume_failed:${resumedOnlineIndexMigration.stdout.trim()}:${resumedOnlineIndexMigration.stderr.trim()}`,
    );
    await assertWorkspaceAuditUpgrade(legalClient);

    const tamperedChecksum = `0${HUMAN_MEMORY_SCHEMA_V1_CHECKSUM.slice(1)}`;
    assert.notEqual(tamperedChecksum, HUMAN_MEMORY_SCHEMA_V1_CHECKSUM);
    const driftDsn = scopedDsn(dsn, driftSchema);
    const driftClient = new Client({
      connectionString: driftDsn,
      ...connectionOptions,
      application_name: "agentops-mis-schema-upgrade-contract-drift",
    });
    clients.push(driftClient);
    await driftClient.connect();
    await createV1Fixture(driftClient, migrationSql, tamperedChecksum);
    const driftMigration = await runMigrator(driftDsn);
    assert.notEqual(driftMigration.exitCode, 0);
    assert.match(
      `${driftMigration.stdout}\n${driftMigration.stderr}`,
      /"error":"human_memory_schema_receipt_drift"/,
    );
    await assertNoWorkspaceAuditUpgrade(driftClient, tamperedChecksum);

    output({
      ok: true,
      contract: "human_memory_schema_v1_v2_v3_to_v4_upgrade_v1",
      checks: {
        exact_v1_receipt_upgraded: true,
        exact_v2_receipt_upgraded: true,
        exact_v3_receipt_upgraded: true,
        latest_v4_receipt_written: true,
        approval_idempotency_table_ready: true,
        approval_kind_is_explicit_without_default: true,
        five_approval_kinds_backfilled: true,
        deferred_approval_binding_triggers_ready: true,
        enrollment_approval_unique_binding_enforced: true,
        approval_execution_binding_immutable: true,
        unclassified_legacy_approval_fails_closed_without_trusted_audit_evidence: true,
        mismatched_prefilled_approval_kind_fails_closed: true,
        audit_workspace_column_constraint_and_online_index_ready: true,
        online_index_stage_resumes_after_receipt: true,
        blocking_index_ddl_absent_from_core_transaction: true,
        schema_readiness_passed: true,
        tampered_v1_receipt_rejected_without_ddl: true,
      },
      credentials_omitted: true,
    });
  } finally {
    for (const client of clients.reverse()) {
      await client.end().catch(() => undefined);
    }
    for (const schema of schemasCreated.reverse()) {
      await admin.query(`DROP SCHEMA ${quotedIdentifier(schema)} CASCADE`).catch(() => undefined);
    }
    await admin.end().catch(() => undefined);
  }
}

main().catch((error: unknown) => {
  const code = error instanceof Error && /^[a-z0-9_]+$/.test(error.message)
    ? error.message
    : "schema_migration_upgrade_contract_failed";
  output({ ok: false, error: code, credentials_omitted: true });
  process.exitCode = 1;
});
