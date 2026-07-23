import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { Client, type ClientConfig } from "pg";

import { postgresDsn, postgresSslEnabled } from "./config";

export type SchemaCommand = "migrate" | "check";

type MigrationDefinition = Readonly<{
  component: string;
  version: string;
  schemaContract: string;
  filename: string;
  checksum: string;
}>;

type LoadedMigration = MigrationDefinition & Readonly<{ sql: string }>;

export type SchemaReceipt = Readonly<{
  contract: "agentops_postgres_schema_readiness_v1";
  ok: true;
  operation: SchemaCommand;
  schema_contract: string;
  manifest_count: number;
  applied_count: number;
  current_count: number;
  lock_acquired: true;
  read_only: boolean;
  credentials_omitted: true;
  sql_omitted: true;
  row_data_omitted: true;
}>;

export class SchemaReadinessError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = "SchemaReadinessError";
    this.code = code;
  }
}

export const SCHEMA_CONTRACT = "agentops_commercial_postgres_v8";

export const POSTGRES_MIGRATION_MANIFEST = Object.freeze([
  {
    component: "commercial_control_plane_baseline",
    version: "20260724.1",
    schemaContract: "current_main_commercial_baseline_v1",
    filename: "20260724_current_main_commercial_baseline.sql",
    checksum: "da149c133e6d731c446650fa1dc50973e54e5a9b786369b0db5af4d7951ae068",
  },
  {
    component: "human_session_memory_review",
    version: "20260718.1",
    schemaContract: "human_session_memory_review_v1",
    filename: "20260718_human_session_memory_review.sql",
    checksum: "8b9e121ce6615fb9475b494b534cad6e1fca84bb9c01b70fe896bc87debe196f",
  },
  {
    component: "workspace_read_models",
    version: "20260719.2",
    schemaContract: "workspace_read_models_v2",
    filename: "20260719_workspace_read_models_v2.sql",
    checksum: "cd2115869682fe44d37b00344023446d001a4cf8df034f5ae0a1044584659e0a",
  },
  {
    component: "human_approval_decisions",
    version: "20260719.3",
    schemaContract: "human_approval_decisions_v3",
    filename: "20260719_human_approval_decisions_v3.sql",
    checksum: "bb88014418b69754908dcaeccdca88e37b0819f938053f11ddf9a7e9cba32124",
  },
  {
    component: "approval_kind_bindings",
    version: "20260719.4",
    schemaContract: "approval_kind_bindings_v4",
    filename: "20260719_approval_kind_bindings_v4.sql",
    checksum: "c68d80f35a1b58943d3dc489b5fa5135a9b9f5042723a5146facabc8ccafffaf",
  },
  {
    component: "customer_delivery_run_unique",
    version: "20260724.5",
    schemaContract: "customer_delivery_run_unique_v5",
    filename: "20260724_customer_delivery_run_unique_v5.sql",
    checksum: "bd1ab7a550a9ab135c4058113a63dc621f1ae1558fa1060d6a4deed3cfd5a284",
  },
  {
    component: "prepared_action_execution_leases",
    version: "20260724.6",
    schemaContract: "prepared_action_execution_leases_v6",
    filename: "20260724_prepared_action_execution_leases_v6.sql",
    checksum: "4165407bbe609f1c30cf7a420e4efb8cfd5f789059645caa0b6b92ffff8bec1d",
  },
  {
    component: "governed_knowledge_index",
    version: "20260724.7",
    schemaContract: "governed_knowledge_index_v7",
    filename: "20260724_governed_knowledge_index_v7.sql",
    checksum: "ea0c543d7a1151d52e8262afc1141fd60f9b7520d5efff5783a82b7335b4bb56",
  },
  {
    component: "worker_evidence_workspace",
    version: "20260724.8",
    schemaContract: "worker_evidence_workspace_v8",
    filename: "20260724_worker_evidence_workspace_v8.sql",
    checksum: "ad5c15c636f15395d71a614478acbcdf7361604156362bb8c1f21d4c34b03d11",
  },
] satisfies readonly MigrationDefinition[]);

const REQUIRED_RELATIONS = Object.freeze([
  "users",
  "agents",
  "tasks",
  "agent_plans",
  "runs",
  "tool_calls",
  "approvals",
  "prepared_actions",
  "prepared_action_execution_leases",
  "prepared_action_execution_receipts",
  "knowledge_documents",
  "knowledge_chunks",
  "memories",
  "evaluations",
  "artifacts",
  "audit_logs",
  "runtime_connectors",
  "runtime_events",
  "agent_gateway_tokens",
  "agent_gateway_sessions",
  "agent_gateway_enrollment_requests",
  "plan_evidence_manifests",
  "workspace_memberships",
  "human_login_credentials",
  "human_sessions",
  "human_login_throttle",
  "human_memory_review_requests",
  "human_approval_decision_requests",
  "idx_audit_logs_workspace_created",
  "idx_approvals_customer_delivery_run_unique",
]);

const REQUIRED_LEDGER_COLUMNS = Object.freeze([
  "component",
  "version",
  "schema_contract",
  "checksum",
  "applied_at",
]);

const REQUIRED_COLUMNS = Object.freeze([
  ["approvals", "approval_kind"],
  ["memories", "workspace_id"],
  ["memories", "run_id"],
  ["runtime_events", "workspace_id"],
] as const);

const MIGRATION_ROOT = fileURLToPath(
  new URL("../../../../../migrations/postgres/", import.meta.url),
);
const ADVISORY_LOCK_KEY = "7157544864185932631";

function sha256(value: string) {
  return createHash("sha256").update(value).digest("hex");
}

async function loadManifest(): Promise<readonly LoadedMigration[]> {
  const loaded: LoadedMigration[] = [];
  for (const migration of POSTGRES_MIGRATION_MANIFEST) {
    let sql: string;
    try {
      sql = await readFile(`${MIGRATION_ROOT}${migration.filename}`, "utf8");
    } catch {
      throw new SchemaReadinessError("migration_file_missing");
    }
    if (sha256(sql) !== migration.checksum) {
      throw new SchemaReadinessError("migration_file_checksum_mismatch");
    }
    loaded.push({ ...migration, sql });
  }
  return loaded;
}

function clientConfig(connectionString?: string): ClientConfig {
  let resolvedConnectionString = connectionString;
  if (!resolvedConnectionString) {
    try {
      resolvedConnectionString = postgresDsn();
    } catch {
      throw new SchemaReadinessError("postgres_dsn_required");
    }
  }
  return {
    connectionString: resolvedConnectionString,
    application_name: "agentops-commercial-schema-runner",
    ssl: postgresSslEnabled() ? { rejectUnauthorized: true } : undefined,
  };
}

async function acquireTransactionLock(client: Client) {
  await client.query("SET LOCAL lock_timeout = '5s'");
  await client.query("SET LOCAL statement_timeout = '45s'");
  await client.query("SELECT pg_advisory_xact_lock($1::bigint)", [ADVISORY_LOCK_KEY]);
}

async function ledgerExists(client: Client) {
  const result = await client.query<{ relation: string | null }>(
    "SELECT to_regclass('agentops_schema_migrations')::text AS relation",
  );
  return result.rows[0]?.relation !== null;
}

async function assertLedgerShape(client: Client) {
  const result = await client.query<{ column_name: string }>(
    `SELECT column_name
       FROM information_schema.columns
      WHERE table_schema=current_schema()
        AND table_name='agentops_schema_migrations'`,
  );
  const actual = new Set(result.rows.map((row) => row.column_name));
  if (REQUIRED_LEDGER_COLUMNS.some((column) => !actual.has(column))) {
    throw new SchemaReadinessError("schema_ledger_shape_mismatch");
  }
}

type LedgerRow = {
  component: string;
  version: string;
  schema_contract: string;
  checksum: string;
};

async function readLedger(client: Client) {
  const components = POSTGRES_MIGRATION_MANIFEST.map((migration) => migration.component);
  const result = await client.query<LedgerRow>(
    `SELECT component,version,schema_contract,checksum
       FROM agentops_schema_migrations
      WHERE component=ANY($1::text[])
      ORDER BY component`,
    [components],
  );
  return new Map(result.rows.map((row) => [row.component, row]));
}

function assertLedgerEntry(migration: MigrationDefinition, row: LedgerRow | undefined) {
  if (!row) return;
  if (
    row.version !== migration.version
    || row.schema_contract !== migration.schemaContract
    || row.checksum !== migration.checksum
  ) {
    throw new SchemaReadinessError("schema_ledger_mismatch");
  }
}

async function recordMigration(client: Client, migration: MigrationDefinition) {
  await client.query(
    `INSERT INTO agentops_schema_migrations(
       component,version,schema_contract,checksum,applied_at
     ) VALUES(
       $1,$2,$3,$4,
       to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
     )`,
    [
      migration.component,
      migration.version,
      migration.schemaContract,
      migration.checksum,
    ],
  );
}

async function assertSchemaRelations(client: Client) {
  const result = await client.query<{ relation_name: string; relation: string | null }>(
    `SELECT relation_name,to_regclass(relation_name)::text AS relation
       FROM unnest($1::text[]) AS relation_name`,
    [REQUIRED_RELATIONS],
  );
  if (result.rows.some((row) => row.relation === null)) {
    throw new SchemaReadinessError("schema_relation_missing");
  }

  for (const [tableName, columnName] of REQUIRED_COLUMNS) {
    const column = await client.query<{ present: boolean }>(
      `SELECT EXISTS(
         SELECT 1
           FROM information_schema.columns
          WHERE table_schema=current_schema()
            AND table_name=$1
            AND column_name=$2
       ) AS present`,
      [tableName, columnName],
    );
    if (!column.rows[0]?.present) {
      throw new SchemaReadinessError("schema_column_missing");
    }
  }
}

async function migrate(client: Client, manifest: readonly LoadedMigration[]) {
  let appliedCount = 0;
  let currentCount = 0;

  for (const migration of manifest) {
    let rows = new Map<string, LedgerRow>();
    if (await ledgerExists(client)) {
      await assertLedgerShape(client);
      rows = await readLedger(client);
    }

    const recorded = rows.get(migration.component);
    assertLedgerEntry(migration, recorded);
    if (recorded) {
      currentCount += 1;
      continue;
    }

    await client.query(migration.sql);
    if (!(await ledgerExists(client))) {
      throw new SchemaReadinessError("schema_ledger_missing_after_migration");
    }
    await assertLedgerShape(client);
    await recordMigration(client, migration);
    appliedCount += 1;
  }

  return { appliedCount, currentCount };
}

async function check(client: Client) {
  if (!(await ledgerExists(client))) {
    throw new SchemaReadinessError("schema_ledger_missing");
  }
  await assertLedgerShape(client);
  const rows = await readLedger(client);
  for (const migration of POSTGRES_MIGRATION_MANIFEST) {
    const recorded = rows.get(migration.component);
    if (!recorded) {
      throw new SchemaReadinessError("schema_ledger_behind");
    }
    assertLedgerEntry(migration, recorded);
  }
  return { appliedCount: 0, currentCount: rows.size };
}

export async function runPostgresSchemaCommand(
  operation: SchemaCommand,
  options: Readonly<{ connectionString?: string }> = {},
): Promise<SchemaReceipt> {
  const manifest = await loadManifest();
  const client = new Client(clientConfig(options.connectionString));
  await client.connect();
  try {
    await client.query(operation === "check" ? "BEGIN READ ONLY" : "BEGIN");
    try {
      await acquireTransactionLock(client);
      const counts = operation === "check"
        ? await check(client)
        : await migrate(client, manifest);
      await assertSchemaRelations(client);
      await client.query(operation === "check" ? "ROLLBACK" : "COMMIT");
      return {
        contract: "agentops_postgres_schema_readiness_v1",
        ok: true,
        operation,
        schema_contract: SCHEMA_CONTRACT,
        manifest_count: manifest.length,
        applied_count: counts.appliedCount,
        current_count: counts.currentCount,
        lock_acquired: true,
        read_only: operation === "check",
        credentials_omitted: true,
        sql_omitted: true,
        row_data_omitted: true,
      };
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      if (error instanceof SchemaReadinessError) throw error;
      throw new SchemaReadinessError(
        operation === "check" ? "schema_check_failed" : "schema_migration_failed",
      );
    }
  } finally {
    await client.end().catch(() => undefined);
  }
}
