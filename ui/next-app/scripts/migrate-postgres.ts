import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { Client } from "pg";
import type { PoolClient } from "pg";

import {
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
  HUMAN_MEMORY_SCHEMA_V4_CHECKSUM,
  HUMAN_MEMORY_SCHEMA_V4_CONTRACT,
  HUMAN_MEMORY_SCHEMA_V4_VERSION,
  assertHumanMemorySchemaCoreReady,
  assertHumanMemorySchemaReady,
  SchemaReadinessError,
} from "../src/server/controlPlane/schemaReadiness";

const BASE_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260718_human_session_memory_review.sql", import.meta.url),
);
const UPGRADE_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260719_workspace_read_models_v2.sql", import.meta.url),
);
const ONLINE_INDEX_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260719_workspace_read_models_v2_online_indexes.sql", import.meta.url),
);
const APPROVAL_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260719_human_approval_decisions_v3.sql", import.meta.url),
);
const APPROVAL_KIND_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260719_approval_kind_bindings_v4.sql", import.meta.url),
);
const CUSTOMER_DELIVERY_UNIQUE_MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260724_customer_delivery_run_unique_v5.sql", import.meta.url),
);

function output(payload: Record<string, unknown>) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

async function ensureAuditWorkspaceIndex(client: Client, migrationSql: string) {
  const existing = await client.query<{ is_valid: boolean; is_ready: boolean }>(
    `SELECT index_record.indisvalid AS is_valid,index_record.indisready AS is_ready
    FROM pg_index index_record
    JOIN pg_class index_relation ON index_relation.oid=index_record.indexrelid
    JOIN pg_namespace namespace ON namespace.oid=index_relation.relnamespace
    WHERE namespace.nspname=current_schema()
      AND index_relation.relname='idx_audit_logs_workspace_created'`,
  );
  const index = existing.rows[0];
  if (existing.rows.length > 1) {
    throw new SchemaReadinessError("human_memory_schema_indexes_mismatch");
  }
  await client.query("SET lock_timeout = '5s'");
  await client.query("SET statement_timeout = '30min'");
  if (index && (!index.is_valid || !index.is_ready)) {
    await client.query("DROP INDEX CONCURRENTLY idx_audit_logs_workspace_created");
  }
  if (!index || !index.is_valid || !index.is_ready) {
    await client.query(migrationSql);
  }
}

async function main() {
  const args = process.argv.slice(2);
  if (args.some((argument) => argument !== "--check")) {
    throw new Error("invalid_migration_arguments");
  }
  const checkOnly = args.includes("--check");
  const baseMigrationBytes = await readFile(BASE_MIGRATION_PATH);
  const upgradeMigrationBytes = await readFile(UPGRADE_MIGRATION_PATH);
  const onlineIndexMigrationBytes = await readFile(ONLINE_INDEX_MIGRATION_PATH);
  const approvalMigrationBytes = await readFile(APPROVAL_MIGRATION_PATH);
  const approvalKindMigrationBytes = await readFile(APPROVAL_KIND_MIGRATION_PATH);
  const customerDeliveryUniqueMigrationBytes = await readFile(CUSTOMER_DELIVERY_UNIQUE_MIGRATION_PATH);
  const baseMigrationChecksum = createHash("sha256").update(baseMigrationBytes).digest("hex");
  const upgradeMigrationChecksum = createHash("sha256").update(upgradeMigrationBytes).digest("hex");
  const onlineIndexMigrationChecksum = createHash("sha256").update(onlineIndexMigrationBytes).digest("hex");
  const approvalMigrationChecksum = createHash("sha256").update(approvalMigrationBytes).digest("hex");
  const approvalKindMigrationChecksum = createHash("sha256").update(approvalKindMigrationBytes).digest("hex");
  const customerDeliveryUniqueMigrationChecksum = createHash("sha256")
    .update(customerDeliveryUniqueMigrationBytes)
    .digest("hex");
  if (baseMigrationChecksum !== HUMAN_MEMORY_SCHEMA_V1_CHECKSUM
    || upgradeMigrationChecksum !== HUMAN_MEMORY_SCHEMA_V2_CHECKSUM
    || onlineIndexMigrationChecksum !== HUMAN_MEMORY_SCHEMA_ONLINE_INDEX_CHECKSUM
    || approvalMigrationChecksum !== HUMAN_MEMORY_SCHEMA_V3_CHECKSUM
    || approvalKindMigrationChecksum !== HUMAN_MEMORY_SCHEMA_V4_CHECKSUM
    || customerDeliveryUniqueMigrationChecksum !== HUMAN_MEMORY_SCHEMA_CHECKSUM) {
    throw new SchemaReadinessError("human_memory_migration_checksum_mismatch");
  }
  const dsn = String(process.env.AGENTOPS_POSTGRES_DSN || process.env.DATABASE_URL || "").trim();
  if (!dsn) throw new Error("postgres_dsn_required");
  const sslEnabled = ["1", "true", "require", "required", "on"]
    .includes(String(process.env.AGENTOPS_POSTGRES_SSL || "").trim().toLowerCase());
  const client = new Client({
    connectionString: dsn,
    ssl: sslEnabled ? { rejectUnauthorized: true } : undefined,
    application_name: checkOnly ? "agentops-mis-schema-readiness" : "agentops-mis-schema-migration",
  });
  try {
    await client.connect();
    const poolClient = client as unknown as PoolClient;
    if (!checkOnly) {
      const advisoryLockKey = `agentops-schema-migration:${HUMAN_MEMORY_SCHEMA_COMPONENT}`;
      await client.query("SELECT pg_advisory_lock(hashtext($1))", [advisoryLockKey]);
      try {
        await client.query("BEGIN");
        try {
          const receiptTableResult = await client.query<{ exists: boolean }>(
            `SELECT EXISTS(
              SELECT 1 FROM information_schema.tables
              WHERE table_schema=current_schema() AND table_name='agentops_schema_migrations'
            ) AS exists`,
          );
          let receiptRows: Array<{
            version: string;
            schema_contract: string;
            checksum: string;
          }> = [];
          if (receiptTableResult.rows[0]?.exists) {
            try {
              const receiptResult = await client.query<{
                version: string;
                schema_contract: string;
                checksum: string;
              }>(
                `SELECT version,schema_contract,checksum FROM agentops_schema_migrations
                WHERE component=$1 FOR UPDATE`,
                [HUMAN_MEMORY_SCHEMA_COMPONENT],
              );
              receiptRows = receiptResult.rows;
            } catch {
              throw new SchemaReadinessError("human_memory_schema_receipt_drift");
            }
          }
          const receipt = receiptRows[0];
          const exactV1Receipt = receipt
            && receipt.version === HUMAN_MEMORY_SCHEMA_V1_VERSION
            && receipt.schema_contract === HUMAN_MEMORY_SCHEMA_V1_CONTRACT
            && receipt.checksum === HUMAN_MEMORY_SCHEMA_V1_CHECKSUM;
          const exactV2Receipt = receipt
            && receipt.version === HUMAN_MEMORY_SCHEMA_V2_VERSION
            && receipt.schema_contract === HUMAN_MEMORY_SCHEMA_V2_CONTRACT
            && receipt.checksum === HUMAN_MEMORY_SCHEMA_V2_CHECKSUM;
          const exactV3Receipt = receipt
            && receipt.version === HUMAN_MEMORY_SCHEMA_V3_VERSION
            && receipt.schema_contract === HUMAN_MEMORY_SCHEMA_V3_CONTRACT
            && receipt.checksum === HUMAN_MEMORY_SCHEMA_V3_CHECKSUM;
          const exactV4Receipt = receipt
            && receipt.version === HUMAN_MEMORY_SCHEMA_V4_VERSION
            && receipt.schema_contract === HUMAN_MEMORY_SCHEMA_V4_CONTRACT
            && receipt.checksum === HUMAN_MEMORY_SCHEMA_V4_CHECKSUM;
          const exactCurrentReceipt = receipt
            && receipt.version === HUMAN_MEMORY_SCHEMA_VERSION
            && receipt.schema_contract === HUMAN_MEMORY_SCHEMA_CONTRACT
            && receipt.checksum === HUMAN_MEMORY_SCHEMA_CHECKSUM;
          if (receiptRows.length > 1
            || (receipt
              && !exactV1Receipt
              && !exactV2Receipt
              && !exactV3Receipt
              && !exactV4Receipt
              && !exactCurrentReceipt)) {
            throw new SchemaReadinessError("human_memory_schema_receipt_drift");
          }
          if (!receipt) {
            await client.query(baseMigrationBytes.toString("utf8"));
          }
          if (!receipt || exactV1Receipt) {
            await client.query(upgradeMigrationBytes.toString("utf8"));
          }
          if (!receipt || exactV1Receipt || exactV2Receipt) {
            await client.query(approvalMigrationBytes.toString("utf8"));
          }
          if (!receipt || exactV1Receipt || exactV2Receipt || exactV3Receipt) {
            await client.query(approvalKindMigrationBytes.toString("utf8"));
          }
          if (!receipt || exactV1Receipt || exactV2Receipt || exactV3Receipt || exactV4Receipt) {
            await client.query(customerDeliveryUniqueMigrationBytes.toString("utf8"));
          }
          await assertHumanMemorySchemaCoreReady(poolClient);
          if (!receipt) {
            await client.query(
              `INSERT INTO agentops_schema_migrations(
                component,version,schema_contract,checksum,applied_at
              ) VALUES($1,$2,$3,$4,CURRENT_TIMESTAMP::TEXT)`,
              [
                HUMAN_MEMORY_SCHEMA_COMPONENT,
                HUMAN_MEMORY_SCHEMA_VERSION,
                HUMAN_MEMORY_SCHEMA_CONTRACT,
                HUMAN_MEMORY_SCHEMA_CHECKSUM,
              ],
            );
          } else if (exactV1Receipt || exactV2Receipt || exactV3Receipt || exactV4Receipt) {
            await client.query(
              `UPDATE agentops_schema_migrations
              SET version=$1,schema_contract=$2,checksum=$3,applied_at=CURRENT_TIMESTAMP::TEXT
              WHERE component=$4`,
              [
                HUMAN_MEMORY_SCHEMA_VERSION,
                HUMAN_MEMORY_SCHEMA_CONTRACT,
                HUMAN_MEMORY_SCHEMA_CHECKSUM,
                HUMAN_MEMORY_SCHEMA_COMPONENT,
              ],
            );
          }
          await client.query("COMMIT");
        } catch (error) {
          await client.query("ROLLBACK").catch(() => undefined);
          throw error;
        }
        await ensureAuditWorkspaceIndex(client, onlineIndexMigrationBytes.toString("utf8"));
        await assertHumanMemorySchemaReady(poolClient);
      } finally {
        await client.query("SELECT pg_advisory_unlock(hashtext($1))", [advisoryLockKey]).catch(() => undefined);
      }
    }
    const readiness = await assertHumanMemorySchemaReady(poolClient);
    output({
      ok: true,
      operation: checkOnly ? "commercial_schema_readiness" : "commercial_schema_migration",
      ready: true,
      component: readiness.component,
      version: readiness.version,
      schema_contract: readiness.schemaContract,
      migration_checksum: readiness.checksum,
      credentials_omitted: true,
    });
  } finally {
    await client.end().catch(() => undefined);
  }
}

main().catch((error: unknown) => {
  const code = error instanceof SchemaReadinessError
    ? error.code
    : error instanceof Error && /^[a-z0-9_]+$/.test(error.message)
      ? error.message
      : "commercial_schema_migration_failed";
  output({ ok: false, error: code, ready: false, credentials_omitted: true });
  process.exitCode = 1;
});
