import assert from "node:assert/strict";
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
  HUMAN_MEMORY_SCHEMA_V2_CHECKSUM,
  HUMAN_MEMORY_SCHEMA_V3_CHECKSUM,
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

async function createApprovalBindingFixture(client: Client) {
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
      decision TEXT NOT NULL DEFAULT 'pending',
      task_id TEXT NOT NULL,
      run_id TEXT NOT NULL,
      tool_call_id TEXT,
      requested_by_agent_id TEXT,
      approver_user_id TEXT,
      reason TEXT,
      decided_at TEXT
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
    VALUES('task_schema_contract','workspace_schema_contract');
    INSERT INTO runs(run_id,task_id,workspace_id,agent_id)
    VALUES('run_schema_contract','task_schema_contract','workspace_schema_contract','agent_schema_contract');
    INSERT INTO tool_calls(tool_call_id,run_id,agent_id) VALUES
      ('tool_schema_contract','run_schema_contract','agent_schema_contract'),
      ('tool_prepared_schema_contract','run_schema_contract','agent_schema_contract');
    INSERT INTO approvals(
      approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,reason
    ) VALUES
      ('approval_run_schema_contract','task_schema_contract','run_schema_contract',NULL,'agent_schema_contract','run review'),
      ('approval_tool_schema_contract','task_schema_contract','run_schema_contract','tool_schema_contract','agent_schema_contract','tool review'),
      ('approval_prepared_schema_contract','task_schema_contract','run_schema_contract','tool_prepared_schema_contract','agent_schema_contract','prepared action review'),
      ('approval_enrollment_schema_contract','task_schema_contract','run_schema_contract',NULL,'agent_schema_contract','enrollment review'),
      ('approval_delivery_schema_contract','task_schema_contract','run_schema_contract',NULL,'agent_schema_contract','delivery review');
    INSERT INTO prepared_actions(
      prepared_action_id,workspace_id,task_id,run_id,tool_call_id,approval_id,requested_by_agent_id
    ) VALUES(
      'prepared_schema_contract','workspace_schema_contract','task_schema_contract',
      'run_schema_contract','tool_prepared_schema_contract','approval_prepared_schema_contract',
      'agent_schema_contract'
    );
    INSERT INTO agent_gateway_enrollment_requests(
      request_id,approval_id,task_id,run_id,workspace_id,agent_id
    ) VALUES(
      'enrollment_schema_contract','approval_enrollment_schema_contract','task_schema_contract',
      'run_schema_contract','workspace_schema_contract','agent_schema_contract'
    );
    INSERT INTO audit_logs(audit_id,entity_type,entity_id,action,metadata_json,created_at)
    VALUES
      (
        'audit_run_schema_contract','approvals','approval_run_schema_contract',
        'agent_gateway.approval_request',
        '{"workspace_id":"workspace_schema_contract"}','2026-07-19T00:00:00Z'
      ),
      (
        'audit_delivery_schema_contract','approvals','approval_delivery_schema_contract',
        'workflow.customer_worker_task.delivery_approval',
        '{"workspace_id":"workspace_schema_contract"}','2026-07-19T00:00:00Z'
      );
  `);
}

async function assertApprovalKindsBackfilled(client: Client) {
  const result = await client.query<{ approval_id: string; approval_kind: string }>(
    `SELECT approval_id,approval_kind FROM approvals ORDER BY approval_id`,
  );
  assert.deepEqual(result.rows, [
    { approval_id: "approval_delivery_schema_contract", approval_kind: "customer_delivery" },
    { approval_id: "approval_enrollment_schema_contract", approval_kind: "agent_enrollment" },
    { approval_id: "approval_prepared_schema_contract", approval_kind: "prepared_action" },
    { approval_id: "approval_run_schema_contract", approval_kind: "run_execution" },
    { approval_id: "approval_tool_schema_contract", approval_kind: "tool_execution" },
  ]);
}

async function main() {
  const dsn = String(process.env.AGENTOPS_POSTGRES_DSN || process.env.DATABASE_URL || "").trim();
  if (!dsn) throw new Error("postgres_dsn_required");
  const sslEnabled = ["1", "true", "require", "required", "on"]
    .includes(String(process.env.AGENTOPS_POSTGRES_SSL || "").trim().toLowerCase());
  const baseMigrationBytes = await readFile(BASE_MIGRATION_PATH);
  const upgradeMigrationBytes = await readFile(UPGRADE_MIGRATION_PATH);
  const onlineIndexMigrationBytes = await readFile(ONLINE_INDEX_MIGRATION_PATH);
  const approvalMigrationBytes = await readFile(APPROVAL_MIGRATION_PATH);
  const approvalKindMigrationBytes = await readFile(APPROVAL_KIND_MIGRATION_PATH);
  const baseMigrationChecksum = createHash("sha256").update(baseMigrationBytes).digest("hex");
  const upgradeMigrationChecksum = createHash("sha256").update(upgradeMigrationBytes).digest("hex");
  const onlineIndexMigrationChecksum = createHash("sha256").update(onlineIndexMigrationBytes).digest("hex");
  const approvalMigrationChecksum = createHash("sha256").update(approvalMigrationBytes).digest("hex");
  const approvalKindMigrationChecksum = createHash("sha256")
    .update(approvalKindMigrationBytes)
    .digest("hex");
  if (baseMigrationChecksum !== HUMAN_MEMORY_SCHEMA_V1_CHECKSUM
    || upgradeMigrationChecksum !== HUMAN_MEMORY_SCHEMA_V2_CHECKSUM
    || onlineIndexMigrationChecksum !== HUMAN_MEMORY_SCHEMA_ONLINE_INDEX_CHECKSUM
    || approvalMigrationChecksum !== HUMAN_MEMORY_SCHEMA_V3_CHECKSUM
    || approvalKindMigrationChecksum !== HUMAN_MEMORY_SCHEMA_CHECKSUM) {
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
    await createApprovalBindingFixture(client);
    await client.query(baseMigrationBytes.toString("utf8"));
    await client.query(upgradeMigrationBytes.toString("utf8"));
    await client.query(onlineIndexMigrationBytes.toString("utf8"));
    await client.query(approvalMigrationBytes.toString("utf8"));
    await client.query(approvalKindMigrationBytes.toString("utf8"));
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
    await assertApprovalKindsBackfilled(client);

    await client.query(
      "ALTER TABLE approvals ALTER COLUMN approval_kind SET DEFAULT 'tool_execution'",
    );
    await expectReadinessFailure(poolClient, "human_memory_schema_approval_kind_column_mismatch");
    await client.query("ALTER TABLE approvals ALTER COLUMN approval_kind DROP DEFAULT");
    await assertHumanMemorySchemaReady(poolClient);

    await client.query(`
      ALTER TABLE approvals DROP CONSTRAINT approvals_kind_binding_check;
      ALTER TABLE approvals ADD CONSTRAINT approvals_kind_binding_check
      CHECK(approval_kind IN (
        'run_execution','tool_execution','prepared_action','agent_enrollment','customer_delivery'
      ));
    `);
    await expectReadinessFailure(poolClient, "human_memory_schema_approval_kind_constraint_mismatch");
    await client.query(`
      ALTER TABLE approvals DROP CONSTRAINT approvals_kind_binding_check;
      ALTER TABLE approvals ADD CONSTRAINT approvals_kind_binding_check CHECK (
        (approval_kind IN ('tool_execution','prepared_action') AND tool_call_id IS NOT NULL)
        OR (approval_kind IN ('run_execution','agent_enrollment','customer_delivery') AND tool_call_id IS NULL)
      );
    `);
    await assertHumanMemorySchemaReady(poolClient);

    await client.query(`
      DROP INDEX idx_agent_gateway_enrollment_approval_unique;
      CREATE INDEX idx_agent_gateway_enrollment_approval_unique
      ON agent_gateway_enrollment_requests(approval_id);
    `);
    await expectReadinessFailure(poolClient, "human_memory_schema_enrollment_approval_index_mismatch");
    await client.query(`
      DROP INDEX idx_agent_gateway_enrollment_approval_unique;
      CREATE UNIQUE INDEX idx_agent_gateway_enrollment_approval_unique
      ON agent_gateway_enrollment_requests(approval_id);
    `);
    await assertHumanMemorySchemaReady(poolClient);

    await client.query(`
      DROP TRIGGER enrollment_requests_kind_binding_enforced
      ON agent_gateway_enrollment_requests;
      CREATE TRIGGER enrollment_requests_kind_binding_enforced
      AFTER INSERT OR UPDATE OR DELETE ON agent_gateway_enrollment_requests
      FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_kind_binding();
    `);
    await expectReadinessFailure(poolClient, "human_memory_schema_approval_kind_triggers_mismatch");
    await client.query(`
      DROP TRIGGER enrollment_requests_kind_binding_enforced
      ON agent_gateway_enrollment_requests;
      CREATE CONSTRAINT TRIGGER enrollment_requests_kind_binding_enforced
      AFTER INSERT OR UPDATE OR DELETE ON agent_gateway_enrollment_requests
      DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_kind_binding();
    `);
    await assertHumanMemorySchemaReady(poolClient);

    await client.query(`
      DROP TRIGGER approvals_kind_immutable ON approvals;
      CREATE TRIGGER approvals_kind_immutable
      BEFORE UPDATE OF approval_kind ON approvals
      FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_kind_immutable();
    `);
    await expectReadinessFailure(poolClient, "human_memory_schema_approval_kind_triggers_mismatch");
    await client.query(`
      DROP TRIGGER approvals_kind_immutable ON approvals;
      CREATE TRIGGER approvals_kind_immutable
      BEFORE UPDATE OR DELETE ON approvals
      FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_kind_immutable();
    `);
    await assertHumanMemorySchemaReady(poolClient);

    await client.query(`
      DROP TRIGGER tool_calls_approval_parent_binding_immutable ON tool_calls;
      CREATE TRIGGER tool_calls_approval_parent_binding_immutable
      BEFORE UPDATE OF run_id ON tool_calls
      FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_parent_binding_immutable();
    `);
    await expectReadinessFailure(
      poolClient,
      "human_memory_schema_approval_parent_triggers_mismatch",
    );
    await client.query(`
      DROP TRIGGER tool_calls_approval_parent_binding_immutable ON tool_calls;
      CREATE TRIGGER tool_calls_approval_parent_binding_immutable
      BEFORE UPDATE OF tool_call_id,run_id,agent_id ON tool_calls
      FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_parent_binding_immutable();
    `);
    await assertHumanMemorySchemaReady(poolClient);

    await client.query(`
      DROP TRIGGER audit_logs_append_only ON audit_logs;
      CREATE TRIGGER audit_logs_append_only
      BEFORE UPDATE ON audit_logs
      FOR EACH ROW EXECUTE FUNCTION agentops_enforce_audit_log_append_only();
    `);
    await expectReadinessFailure(
      poolClient,
      "human_memory_schema_audit_append_trigger_mismatch",
    );
    await client.query(`
      DROP TRIGGER audit_logs_append_only ON audit_logs;
      CREATE TRIGGER audit_logs_append_only
      BEFORE UPDATE OR DELETE ON audit_logs
      FOR EACH ROW EXECUTE FUNCTION agentops_enforce_audit_log_append_only();
    `);
    await assertHumanMemorySchemaReady(poolClient);

    const originalEvidenceSealFunction = await client.query<{ definition: string }>(
      `SELECT pg_get_functiondef(
        'agentops_enforce_customer_delivery_evidence_seal()'::regprocedure
      ) AS definition`,
    );
    assert.equal(originalEvidenceSealFunction.rows.length, 1);
    await client.query(`
      CREATE OR REPLACE FUNCTION agentops_enforce_customer_delivery_evidence_seal()
      RETURNS TRIGGER
      LANGUAGE plpgsql
      AS $$
      BEGIN
        IF EXISTS(
          SELECT 1 FROM approvals approval
          WHERE approval.approval_kind='customer_delivery'
            AND approval.decision<>'pending'
        ) THEN
          RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='customer_delivery_evidence_sealed';
        END IF;
        RETURN NEW;
      END
      $$;
    `);
    await expectReadinessFailure(
      poolClient,
      "human_memory_schema_approval_kind_functions_mismatch",
    );
    await client.query(originalEvidenceSealFunction.rows[0].definition);
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
      contract: "human_memory_schema_readiness_v4",
      checks: {
        v1_v2_v3_v4_migration_bytes_match_fixed_checksums: true,
        exact_schema_ready: true,
        five_approval_kinds_backfilled: true,
        approval_kind_default_drift_rejected: true,
        weak_approval_kind_binding_constraint_rejected: true,
        non_unique_enrollment_binding_rejected: true,
        non_deferred_binding_trigger_rejected: true,
        weak_approval_binding_immutable_trigger_rejected: true,
        weak_parent_binding_immutable_trigger_rejected: true,
        weak_audit_append_only_trigger_rejected: true,
        update_escape_weak_evidence_seal_function_rejected: true,
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
  const stack = error instanceof Error ? String(error.stack || "") : "";
  const location = stack.match(/schema-readiness-contract\.ts:\d+:\d+/)?.[0] || null;
  const databaseCode = (error as { code?: string } | undefined)?.code || null;
  const code = error instanceof SchemaReadinessError
    ? error.code
    : error instanceof Error && /^[a-z0-9_]+$/.test(error.message)
      ? error.message
      : "schema_readiness_contract_failed";
  output({
    ok: false,
    error: code,
    location,
    database_code: databaseCode,
    credentials_omitted: true,
  });
  process.exitCode = 1;
});
