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
  HUMAN_MEMORY_SCHEMA_VERSION,
  assertHumanMemorySchemaReady,
  assertHumanMemorySchemaStructureReady,
  SchemaReadinessError,
} from "../src/server/controlPlane/schemaReadiness";

const MIGRATION_PATH = fileURLToPath(
  new URL("../../../migrations/postgres/20260718_human_session_memory_review.sql", import.meta.url),
);

function output(payload: Record<string, unknown>) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

async function main() {
  const args = process.argv.slice(2);
  if (args.some((argument) => argument !== "--check")) {
    throw new Error("invalid_migration_arguments");
  }
  const checkOnly = args.includes("--check");
  const migrationBytes = await readFile(MIGRATION_PATH);
  const migrationChecksum = createHash("sha256").update(migrationBytes).digest("hex");
  if (migrationChecksum !== HUMAN_MEMORY_SCHEMA_CHECKSUM) {
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
      await client.query("BEGIN");
      try {
        await client.query(
          "SELECT pg_advisory_xact_lock(hashtext($1))",
          [`agentops-schema-migration:${HUMAN_MEMORY_SCHEMA_COMPONENT}`],
        );
        await client.query(migrationBytes.toString("utf8"));
        await assertHumanMemorySchemaStructureReady(poolClient);
        const receiptResult = await client.query<{
          version: string;
          schema_contract: string;
          checksum: string;
        }>(
          `SELECT version,schema_contract,checksum FROM agentops_schema_migrations
          WHERE component=$1 FOR UPDATE`,
          [HUMAN_MEMORY_SCHEMA_COMPONENT],
        );
        const receipt = receiptResult.rows[0];
        if (receiptResult.rows.length > 1
          || (receipt && (
            receipt.version !== HUMAN_MEMORY_SCHEMA_VERSION
            || receipt.schema_contract !== HUMAN_MEMORY_SCHEMA_CONTRACT
            || receipt.checksum !== HUMAN_MEMORY_SCHEMA_CHECKSUM
          ))) {
          throw new SchemaReadinessError("human_memory_schema_receipt_drift");
        }
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
        }
        await assertHumanMemorySchemaReady(poolClient);
        await client.query("COMMIT");
      } catch (error) {
        await client.query("ROLLBACK").catch(() => undefined);
        throw error;
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
