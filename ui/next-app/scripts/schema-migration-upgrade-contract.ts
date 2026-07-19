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

async function createV1Fixture(
  client: Client,
  migrationSql: string,
  receiptChecksum: string,
) {
  await client.query(`
    CREATE TABLE users(user_id TEXT PRIMARY KEY);
    CREATE TABLE memories(memory_id TEXT PRIMARY KEY);
    CREATE TABLE audit_logs(
      audit_id TEXT PRIMARY KEY,
      metadata_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL
    );
  `);
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

  await assertHumanMemorySchemaReady(client as unknown as PoolClient);
}

async function assertNoWorkspaceAuditUpgrade(client: Client, tamperedChecksum: string) {
  const column = await client.query<{ count: string }>(
    `SELECT COUNT(*)::TEXT AS count FROM information_schema.columns
    WHERE table_schema=current_schema()
      AND table_name='audit_logs' AND column_name='workspace_id'`,
  );
  assert.equal(column.rows[0]?.count, "0");

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
  assert.equal(v2MigrationChecksum, HUMAN_MEMORY_SCHEMA_CHECKSUM);
  const onlineIndexMigrationBytes = await readFile(ONLINE_INDEX_MIGRATION_PATH);
  const onlineIndexMigrationChecksum = createHash("sha256").update(onlineIndexMigrationBytes).digest("hex");
  assert.equal(onlineIndexMigrationChecksum, HUMAN_MEMORY_SCHEMA_ONLINE_INDEX_CHECKSUM);
  assert.match(v2MigrationBytes.toString("utf8"), /SET LOCAL lock_timeout = '5s'/);
  assert.doesNotMatch(v2MigrationBytes.toString("utf8"), /CREATE INDEX/);
  assert.match(onlineIndexMigrationBytes.toString("utf8"), /CREATE INDEX CONCURRENTLY/);
  const migrationSql = migrationBytes.toString("utf8");
  const legalSchema = `agentops_schema_upgrade_${randomBytes(8).toString("hex")}`;
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
    for (const schema of [legalSchema, driftSchema]) {
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
      contract: "human_memory_schema_v1_to_v2_upgrade_v1",
      checks: {
        exact_v1_receipt_upgraded: true,
        latest_receipt_written: true,
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
