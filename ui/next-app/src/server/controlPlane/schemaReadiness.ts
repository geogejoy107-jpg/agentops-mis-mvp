import type { PoolClient } from "pg";

export const HUMAN_MEMORY_SCHEMA_COMPONENT = "human_session_memory_review";
export const HUMAN_MEMORY_SCHEMA_V1_VERSION = "20260718_human_session_memory_review_v1";
export const HUMAN_MEMORY_SCHEMA_V1_CONTRACT = "agentops-human-session-memory-review-contract-v1";
export const HUMAN_MEMORY_SCHEMA_V1_CHECKSUM = "6203fe8813acbdf048da59e17193df74fd6a52c5b7c998e35b0355b9e90aba69";
export const HUMAN_MEMORY_SCHEMA_VERSION = "20260719_workspace_read_models_v2";
export const HUMAN_MEMORY_SCHEMA_CONTRACT = "agentops-human-session-workspace-read-models-contract-v2";
export const HUMAN_MEMORY_SCHEMA_CHECKSUM = "d3da5e4b3597c38a0e9261636b363a36bf9b58e4354f3363896aded0bec2dd58";
export const HUMAN_MEMORY_SCHEMA_ONLINE_INDEX_CHECKSUM = "6f37e786f1394e6e3e229374aca90fe6b7bb7d2b576f7e33cb8e35164c77fc95";

type RequiredColumn = {
  dataType: "text" | "integer";
  nullable: boolean;
};

const REQUIRED_COLUMNS: Record<string, Record<string, RequiredColumn>> = {
  agentops_schema_migrations: {
    component: { dataType: "text", nullable: false },
    version: { dataType: "text", nullable: false },
    schema_contract: { dataType: "text", nullable: false },
    checksum: { dataType: "text", nullable: false },
    applied_at: { dataType: "text", nullable: false },
  },
  workspace_memberships: {
    workspace_id: { dataType: "text", nullable: false },
    user_id: { dataType: "text", nullable: false },
    role: { dataType: "text", nullable: false },
    status: { dataType: "text", nullable: false },
    created_at: { dataType: "text", nullable: false },
    updated_at: { dataType: "text", nullable: false },
  },
  human_login_credentials: {
    credential_id: { dataType: "text", nullable: false },
    user_id: { dataType: "text", nullable: false },
    username: { dataType: "text", nullable: false },
    password_hash: { dataType: "text", nullable: false },
    password_salt: { dataType: "text", nullable: false },
    password_params_json: { dataType: "text", nullable: false },
    status: { dataType: "text", nullable: false },
    created_at: { dataType: "text", nullable: false },
    updated_at: { dataType: "text", nullable: false },
    last_login_at: { dataType: "text", nullable: true },
  },
  human_sessions: {
    session_id: { dataType: "text", nullable: false },
    user_id: { dataType: "text", nullable: false },
    session_hash: { dataType: "text", nullable: false },
    status: { dataType: "text", nullable: false },
    created_at: { dataType: "text", nullable: false },
    expires_at: { dataType: "text", nullable: false },
    last_seen_at: { dataType: "text", nullable: true },
    revoked_at: { dataType: "text", nullable: true },
  },
  human_login_throttle: {
    bucket_key: { dataType: "text", nullable: false },
    failure_count: { dataType: "integer", nullable: false },
    window_started_at: { dataType: "text", nullable: false },
    blocked_until: { dataType: "text", nullable: true },
    updated_at: { dataType: "text", nullable: false },
  },
  human_memory_review_requests: {
    workspace_id: { dataType: "text", nullable: false },
    user_id: { dataType: "text", nullable: false },
    idempotency_key_hash: { dataType: "text", nullable: false },
    request_hash: { dataType: "text", nullable: false },
    memory_id: { dataType: "text", nullable: false },
    decision: { dataType: "text", nullable: false },
    status: { dataType: "text", nullable: false },
    created_at: { dataType: "text", nullable: false },
    completed_at: { dataType: "text", nullable: true },
  },
};

type RequiredConstraint = {
  tableName: string;
  constraintName: string;
  constraintType: "c" | "f" | "p" | "u";
  definition: string;
};

const REQUIRED_CONSTRAINTS: RequiredConstraint[] = [
  {
    tableName: "agentops_schema_migrations",
    constraintName: "agentops_schema_migrations_pkey",
    constraintType: "p",
    definition: "PRIMARY KEY (component)",
  },
  {
    tableName: "agentops_schema_migrations",
    constraintName: "agentops_schema_migrations_checksum_check",
    constraintType: "c",
    definition: "CHECK (checksum ~ '^[a-f0-9]{64}$'::text)",
  },
  {
    tableName: "workspace_memberships",
    constraintName: "workspace_memberships_pkey",
    constraintType: "p",
    definition: "PRIMARY KEY (workspace_id, user_id)",
  },
  {
    tableName: "workspace_memberships",
    constraintName: "workspace_memberships_role_check",
    constraintType: "c",
    definition: "CHECK (role = ANY (ARRAY['viewer'::text, 'operator'::text, 'approver'::text, 'owner'::text]))",
  },
  {
    tableName: "workspace_memberships",
    constraintName: "workspace_memberships_status_check",
    constraintType: "c",
    definition: "CHECK (status = ANY (ARRAY['active'::text, 'disabled'::text]))",
  },
  {
    tableName: "workspace_memberships",
    constraintName: "workspace_memberships_user_id_fkey",
    constraintType: "f",
    definition: "FOREIGN KEY (user_id) REFERENCES users(user_id)",
  },
  {
    tableName: "human_login_credentials",
    constraintName: "human_login_credentials_pkey",
    constraintType: "p",
    definition: "PRIMARY KEY (credential_id)",
  },
  {
    tableName: "human_login_credentials",
    constraintName: "human_login_credentials_user_id_key",
    constraintType: "u",
    definition: "UNIQUE (user_id)",
  },
  {
    tableName: "human_login_credentials",
    constraintName: "human_login_credentials_username_key",
    constraintType: "u",
    definition: "UNIQUE (username)",
  },
  {
    tableName: "human_login_credentials",
    constraintName: "human_login_credentials_username_check",
    constraintType: "c",
    definition: "CHECK (username = lower(username))",
  },
  {
    tableName: "human_login_credentials",
    constraintName: "human_login_credentials_status_check",
    constraintType: "c",
    definition: "CHECK (status = ANY (ARRAY['active'::text, 'disabled'::text]))",
  },
  {
    tableName: "human_login_credentials",
    constraintName: "human_login_credentials_user_id_fkey",
    constraintType: "f",
    definition: "FOREIGN KEY (user_id) REFERENCES users(user_id)",
  },
  {
    tableName: "human_sessions",
    constraintName: "human_sessions_pkey",
    constraintType: "p",
    definition: "PRIMARY KEY (session_id)",
  },
  {
    tableName: "human_sessions",
    constraintName: "human_sessions_session_hash_key",
    constraintType: "u",
    definition: "UNIQUE (session_hash)",
  },
  {
    tableName: "human_sessions",
    constraintName: "human_sessions_status_check",
    constraintType: "c",
    definition: "CHECK (status = ANY (ARRAY['active'::text, 'revoked'::text, 'expired'::text]))",
  },
  {
    tableName: "human_sessions",
    constraintName: "human_sessions_user_id_fkey",
    constraintType: "f",
    definition: "FOREIGN KEY (user_id) REFERENCES users(user_id)",
  },
  {
    tableName: "human_login_throttle",
    constraintName: "human_login_throttle_pkey",
    constraintType: "p",
    definition: "PRIMARY KEY (bucket_key)",
  },
  {
    tableName: "human_login_throttle",
    constraintName: "human_login_throttle_failure_count_check",
    constraintType: "c",
    definition: "CHECK (failure_count >= 0)",
  },
  {
    tableName: "human_memory_review_requests",
    constraintName: "human_memory_review_requests_pkey",
    constraintType: "p",
    definition: "PRIMARY KEY (workspace_id, user_id, idempotency_key_hash)",
  },
  {
    tableName: "human_memory_review_requests",
    constraintName: "human_memory_review_requests_decision_check",
    constraintType: "c",
    definition: "CHECK (decision = ANY (ARRAY['approved'::text, 'rejected'::text]))",
  },
  {
    tableName: "human_memory_review_requests",
    constraintName: "human_memory_review_requests_status_check",
    constraintType: "c",
    definition: "CHECK (status = 'completed'::text)",
  },
  {
    tableName: "human_memory_review_requests",
    constraintName: "human_memory_review_requests_user_id_fkey",
    constraintType: "f",
    definition: "FOREIGN KEY (user_id) REFERENCES users(user_id)",
  },
  {
    tableName: "human_memory_review_requests",
    constraintName: "human_memory_review_requests_memory_id_fkey",
    constraintType: "f",
    definition: "FOREIGN KEY (memory_id) REFERENCES memories(memory_id)",
  },
];

type RequiredIndex = {
  tableName: string;
  indexName: string;
  unique: boolean;
  keys: string[];
};

const REQUIRED_INDEXES: RequiredIndex[] = [
  {
    tableName: "audit_logs",
    indexName: "idx_audit_logs_workspace_created",
    unique: false,
    keys: ["workspace_id", "created_at", "audit_id"],
  },
  {
    tableName: "workspace_memberships",
    indexName: "idx_workspace_memberships_user",
    unique: false,
    keys: ["user_id", "status", "workspace_id"],
  },
  {
    tableName: "workspace_memberships",
    indexName: "idx_workspace_memberships_identity_unique",
    unique: true,
    keys: ["workspace_id", "user_id"],
  },
  {
    tableName: "human_login_credentials",
    indexName: "idx_human_login_credentials_user_unique",
    unique: true,
    keys: ["user_id"],
  },
  {
    tableName: "human_login_credentials",
    indexName: "idx_human_login_credentials_username_unique",
    unique: true,
    keys: ["username"],
  },
  {
    tableName: "human_sessions",
    indexName: "idx_human_sessions_hash_unique",
    unique: true,
    keys: ["session_hash"],
  },
  {
    tableName: "human_sessions",
    indexName: "idx_human_sessions_user",
    unique: false,
    keys: ["user_id", "status", "expires_at"],
  },
  {
    tableName: "human_memory_review_requests",
    indexName: "idx_human_memory_review_memory",
    unique: false,
    keys: ["workspace_id", "memory_id", "created_at"],
  },
  {
    tableName: "human_memory_review_requests",
    indexName: "idx_human_memory_review_idempotency_unique",
    unique: true,
    keys: ["workspace_id", "user_id", "idempotency_key_hash"],
  },
];

type ColumnRow = {
  table_name: string;
  column_name: string;
  data_type: string;
  is_nullable: "YES" | "NO";
};

type ConstraintRow = {
  table_name: string;
  constraint_name: string;
  constraint_type: RequiredConstraint["constraintType"];
  definition: string;
};

type IndexRow = {
  table_name: string;
  index_name: string;
  access_method: string;
  is_unique: boolean;
  is_primary: boolean;
  is_valid: boolean;
  is_ready: boolean;
  key_definitions: string[];
  included_count: number;
  predicate: string | null;
};

function normalizedDefinition(value: string) {
  return value.replace(/\s+/g, " ").trim();
}

export class SchemaReadinessError extends Error {
  constructor(readonly code: string) {
    super("The commercial Human Session schema is not at the exact required version.");
  }
}

async function assertColumnsReady(client: PoolClient) {
  let rows: ColumnRow[];
  try {
    const result = await client.query<ColumnRow>(
      `SELECT table_name,column_name,data_type,is_nullable
      FROM information_schema.columns
      WHERE table_schema=current_schema() AND table_name=ANY($1::text[])`,
      [Object.keys(REQUIRED_COLUMNS)],
    );
    rows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_columns_mismatch");
  }
  const expectedCount = Object.values(REQUIRED_COLUMNS)
    .reduce((count, columns) => count + Object.keys(columns).length, 0);
  if (rows.length !== expectedCount) {
    throw new SchemaReadinessError("human_memory_schema_columns_mismatch");
  }
  for (const row of rows) {
    const expected = REQUIRED_COLUMNS[row.table_name]?.[row.column_name];
    if (!expected
      || row.data_type !== expected.dataType
      || (row.is_nullable === "YES") !== expected.nullable) {
      throw new SchemaReadinessError("human_memory_schema_columns_mismatch");
    }
  }
}

async function assertAuditWorkspaceColumnReady(client: PoolClient) {
  let rows: ColumnRow[];
  try {
    const result = await client.query<ColumnRow>(
      `SELECT table_name,column_name,data_type,is_nullable
      FROM information_schema.columns
      WHERE table_schema=current_schema()
        AND table_name='audit_logs' AND column_name='workspace_id'`,
    );
    rows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_columns_mismatch");
  }
  if (rows.length !== 1
    || rows[0].data_type !== "text"
    || rows[0].is_nullable !== "YES") {
    throw new SchemaReadinessError("human_memory_schema_columns_mismatch");
  }

  let constraints: Array<{ constraint_type: string; validated: boolean; definition: string }>;
  try {
    const result = await client.query<{
      constraint_type: string;
      validated: boolean;
      definition: string;
    }>(
      `SELECT constraint_record.contype AS constraint_type,
        constraint_record.convalidated AS validated,
        pg_get_constraintdef(constraint_record.oid,true) AS definition
      FROM pg_constraint constraint_record
      JOIN pg_class relation ON relation.oid=constraint_record.conrelid
      JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
      WHERE namespace.nspname=current_schema()
        AND relation.relname='audit_logs'
        AND constraint_record.conname='audit_logs_workspace_metadata_match'`,
    );
    constraints = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_constraints_mismatch");
  }
  const constraint = constraints[0];
  const definition = normalizedDefinition(constraint?.definition || "");
  if (constraints.length !== 1
    || constraint.constraint_type !== "c"
    || !constraint.validated
    || !definition.includes("workspace_id IS NULL")
    || !definition.includes("metadata_json")
    || !definition.includes("::jsonb")
    || !definition.includes("->> 'workspace_id'::text")
    || !definition.includes("= workspace_id")) {
    throw new SchemaReadinessError("human_memory_schema_constraints_mismatch");
  }
}

async function assertConstraintsReady(client: PoolClient) {
  let rows: ConstraintRow[];
  try {
    const result = await client.query<ConstraintRow>(
      `SELECT relation.relname AS table_name,constraint_record.conname AS constraint_name,
        constraint_record.contype AS constraint_type,
        pg_get_constraintdef(constraint_record.oid,true) AS definition
      FROM pg_constraint constraint_record
      JOIN pg_class relation ON relation.oid=constraint_record.conrelid
      JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
      WHERE namespace.nspname=current_schema()
        AND relation.relname=ANY($1::text[])
        AND constraint_record.contype=ANY($2::char[])`,
      [Object.keys(REQUIRED_COLUMNS), ["c", "f", "p", "u"]],
    );
    rows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_constraints_mismatch");
  }
  if (rows.length !== REQUIRED_CONSTRAINTS.length) {
    throw new SchemaReadinessError("human_memory_schema_constraints_mismatch");
  }
  const actual = new Map(rows.map((row) => [
    `${row.table_name}.${row.constraint_name}`,
    row,
  ]));
  for (const expected of REQUIRED_CONSTRAINTS) {
    const row = actual.get(`${expected.tableName}.${expected.constraintName}`);
    if (!row
      || row.constraint_type !== expected.constraintType
      || normalizedDefinition(row.definition) !== expected.definition) {
      throw new SchemaReadinessError("human_memory_schema_constraints_mismatch");
    }
  }
}

async function assertIndexesReady(client: PoolClient) {
  let rows: IndexRow[];
  try {
    const result = await client.query<IndexRow>(
      `SELECT table_relation.relname AS table_name,index_relation.relname AS index_name,
        access_method.amname AS access_method,index_record.indisunique AS is_unique,
        index_record.indisprimary AS is_primary,index_record.indisvalid AS is_valid,
        index_record.indisready AS is_ready,
        ARRAY(
          SELECT pg_get_indexdef(index_record.indexrelid,position,true)
          FROM generate_series(1,index_record.indnkeyatts) AS position
          ORDER BY position
        ) AS key_definitions,
        (index_record.indnatts-index_record.indnkeyatts)::integer AS included_count,
        pg_get_expr(index_record.indpred,index_record.indrelid,true) AS predicate
      FROM pg_index index_record
      JOIN pg_class index_relation ON index_relation.oid=index_record.indexrelid
      JOIN pg_class table_relation ON table_relation.oid=index_record.indrelid
      JOIN pg_namespace namespace ON namespace.oid=index_relation.relnamespace
      JOIN pg_am access_method ON access_method.oid=index_relation.relam
      WHERE namespace.nspname=current_schema() AND index_relation.relname=ANY($1::text[])`,
      [REQUIRED_INDEXES.map((index) => index.indexName)],
    );
    rows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_indexes_mismatch");
  }
  if (rows.length !== REQUIRED_INDEXES.length) {
    throw new SchemaReadinessError("human_memory_schema_indexes_mismatch");
  }
  const actual = new Map(rows.map((row) => [row.index_name, row]));
  for (const expected of REQUIRED_INDEXES) {
    const row = actual.get(expected.indexName);
    if (!row
      || row.table_name !== expected.tableName
      || row.access_method !== "btree"
      || row.is_unique !== expected.unique
      || row.is_primary
      || !row.is_valid
      || !row.is_ready
      || row.included_count !== 0
      || row.predicate !== null
      || row.key_definitions.length !== expected.keys.length
      || row.key_definitions.some((key, index) => key !== expected.keys[index])) {
      throw new SchemaReadinessError("human_memory_schema_indexes_mismatch");
    }
  }
}

export async function assertHumanMemorySchemaCoreReady(client: PoolClient) {
  await assertColumnsReady(client);
  await assertAuditWorkspaceColumnReady(client);
  await assertConstraintsReady(client);
}

export async function assertHumanMemorySchemaStructureReady(client: PoolClient) {
  await assertHumanMemorySchemaCoreReady(client);
  await assertIndexesReady(client);
}

export async function assertHumanMemorySchemaReady(client: PoolClient) {
  await assertHumanMemorySchemaStructureReady(client);
  let versionRows: Array<{ version: string; schema_contract: string; checksum: string }>;
  try {
    const result = await client.query<{ version: string; schema_contract: string; checksum: string }>(
      `SELECT version,schema_contract,checksum FROM agentops_schema_migrations
      WHERE component=$1`,
      [HUMAN_MEMORY_SCHEMA_COMPONENT],
    );
    versionRows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_version_missing");
  }
  const migration = versionRows[0];
  if (versionRows.length !== 1
    || migration.version !== HUMAN_MEMORY_SCHEMA_VERSION
    || migration.schema_contract !== HUMAN_MEMORY_SCHEMA_CONTRACT
    || migration.checksum !== HUMAN_MEMORY_SCHEMA_CHECKSUM) {
    throw new SchemaReadinessError("human_memory_schema_version_mismatch");
  }
  return {
    component: HUMAN_MEMORY_SCHEMA_COMPONENT,
    version: HUMAN_MEMORY_SCHEMA_VERSION,
    schemaContract: HUMAN_MEMORY_SCHEMA_CONTRACT,
    checksum: HUMAN_MEMORY_SCHEMA_CHECKSUM,
  };
}
