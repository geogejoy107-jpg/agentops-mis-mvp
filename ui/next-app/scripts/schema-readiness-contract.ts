import { createHash, randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { Client } from "pg";
import type { PoolClient } from "pg";

import {
  assertHumanMemorySchemaReady,
  HUMAN_MEMORY_SCHEMA_CHECKSUM,
  HUMAN_MEMORY_SCHEMA_COMPONENT,
  HUMAN_MEMORY_SCHEMA_CONTRACT,
  HUMAN_MEMORY_SCHEMA_ONLINE_INDEX_CHECKSUM,
  HUMAN_MEMORY_SCHEMA_VERSION,
  HUMAN_MEMORY_SCHEMA_V1_CHECKSUM,
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

function output(payload: Record<string, unknown>) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

async function expectReadinessFailure(client: PoolClient, expectedCode: string) {
  try {
    await assertHumanMemorySchemaReady(client);
  } catch (error) {
    if (error instanceof SchemaReadinessError && error.code === expectedCode) return;
    throw error;
  }
  throw new Error(`expected_${expectedCode}`);
}

async function main() {
  const dsn = String(process.env.AGENTOPS_POSTGRES_DSN || process.env.DATABASE_URL || "").trim();
  if (!dsn) throw new Error("postgres_dsn_required");
  const sslEnabled = ["1", "true", "require", "required", "on"]
    .includes(String(process.env.AGENTOPS_POSTGRES_SSL || "").trim().toLowerCase());
  const baseMigrationBytes = await readFile(BASE_MIGRATION_PATH);
  const upgradeMigrationBytes = await readFile(UPGRADE_MIGRATION_PATH);
  const onlineIndexMigrationBytes = await readFile(ONLINE_INDEX_MIGRATION_PATH);
  const baseMigrationChecksum = createHash("sha256").update(baseMigrationBytes).digest("hex");
  const upgradeMigrationChecksum = createHash("sha256").update(upgradeMigrationBytes).digest("hex");
  const onlineIndexMigrationChecksum = createHash("sha256").update(onlineIndexMigrationBytes).digest("hex");
  if (baseMigrationChecksum !== HUMAN_MEMORY_SCHEMA_V1_CHECKSUM
    || upgradeMigrationChecksum !== HUMAN_MEMORY_SCHEMA_CHECKSUM
    || onlineIndexMigrationChecksum !== HUMAN_MEMORY_SCHEMA_ONLINE_INDEX_CHECKSUM) {
    throw new Error("migration_checksum_fixture_mismatch");
  }

  const schemaName = `agentops_human_schema_contract_${randomBytes(8).toString("hex")}`;
  const quotedSchema = `"${schemaName}"`;
  const client = new Client({
    connectionString: dsn,
    ssl: sslEnabled ? { rejectUnauthorized: true } : undefined,
    application_name: "agentops-mis-schema-readiness-contract",
  });
  let schemaCreated = false;
  try {
    await client.connect();
    await client.query(`CREATE SCHEMA ${quotedSchema}`);
    schemaCreated = true;
    await client.query(`SET search_path TO ${quotedSchema}`);
    await client.query("CREATE TABLE users(user_id TEXT PRIMARY KEY)");
    await client.query("CREATE TABLE memories(memory_id TEXT PRIMARY KEY)");
    await client.query(
      "CREATE TABLE audit_logs(audit_id TEXT PRIMARY KEY,metadata_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL)",
    );
    await client.query(baseMigrationBytes.toString("utf8"));
    await client.query(upgradeMigrationBytes.toString("utf8"));
    await client.query(onlineIndexMigrationBytes.toString("utf8"));
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

    const poolClient = client as unknown as PoolClient;
    await assertHumanMemorySchemaReady(poolClient);

    await client.query(
      `ALTER TABLE workspace_memberships
      DROP CONSTRAINT workspace_memberships_role_check,
      ADD CONSTRAINT workspace_memberships_role_check CHECK(role <> '')`,
    );
    await expectReadinessFailure(poolClient, "human_memory_schema_constraints_mismatch");
    await client.query(
      `ALTER TABLE workspace_memberships
      DROP CONSTRAINT workspace_memberships_role_check,
      ADD CONSTRAINT workspace_memberships_role_check
      CHECK(role IN ('viewer','operator','approver','owner'))`,
    );
    await assertHumanMemorySchemaReady(poolClient);

    await client.query("DROP INDEX idx_human_sessions_user");
    await client.query("CREATE INDEX idx_human_sessions_user ON human_sessions(user_id)");
    await expectReadinessFailure(poolClient, "human_memory_schema_indexes_mismatch");
    await client.query("DROP INDEX idx_human_sessions_user");
    await client.query(
      "CREATE INDEX idx_human_sessions_user ON human_sessions(user_id,status,expires_at)",
    );
    await assertHumanMemorySchemaReady(poolClient);

    await client.query(
      "UPDATE agentops_schema_migrations SET checksum=$1 WHERE component=$2",
      ["0".repeat(64), HUMAN_MEMORY_SCHEMA_COMPONENT],
    );
    await expectReadinessFailure(poolClient, "human_memory_schema_version_mismatch");

    output({
      ok: true,
      contract: "human_memory_schema_readiness_v2",
      checks: {
        base_and_upgrade_migration_bytes_match_fixed_checksums: true,
        exact_schema_ready: true,
        same_name_weak_check_rejected: true,
        same_name_weak_index_rejected: true,
        migration_receipt_checksum_drift_rejected: true,
      },
      credentials_omitted: true,
    });
  } finally {
    if (schemaCreated) {
      await client.query("SET search_path TO public").catch(() => undefined);
      await client.query(`DROP SCHEMA ${quotedSchema} CASCADE`).catch(() => undefined);
    }
    await client.end().catch(() => undefined);
  }
}

main().catch((error: unknown) => {
  const code = error instanceof SchemaReadinessError
    ? error.code
    : error instanceof Error && /^[a-z0-9_]+$/.test(error.message)
      ? error.message
      : "schema_readiness_contract_failed";
  output({ ok: false, error: code, credentials_omitted: true });
  process.exitCode = 1;
});
