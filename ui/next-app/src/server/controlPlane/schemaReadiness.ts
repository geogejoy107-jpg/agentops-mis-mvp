import type { PoolClient } from "pg";

export const HUMAN_MEMORY_SCHEMA_COMPONENT = "human_session_memory_review";
export const HUMAN_MEMORY_SCHEMA_V1_VERSION = "20260718_human_session_memory_review_v1";
export const HUMAN_MEMORY_SCHEMA_V1_CONTRACT = "agentops-human-session-memory-review-contract-v1";
export const HUMAN_MEMORY_SCHEMA_V1_CHECKSUM = "6203fe8813acbdf048da59e17193df74fd6a52c5b7c998e35b0355b9e90aba69";
export const HUMAN_MEMORY_SCHEMA_V2_VERSION = "20260719_workspace_read_models_v2";
export const HUMAN_MEMORY_SCHEMA_V2_CONTRACT = "agentops-human-session-workspace-read-models-contract-v2";
export const HUMAN_MEMORY_SCHEMA_V2_CHECKSUM = "d3da5e4b3597c38a0e9261636b363a36bf9b58e4354f3363896aded0bec2dd58";
export const HUMAN_MEMORY_SCHEMA_V3_VERSION = "20260719_human_approval_decisions_v3";
export const HUMAN_MEMORY_SCHEMA_V3_CONTRACT = "agentops-human-session-approval-decisions-contract-v3";
export const HUMAN_MEMORY_SCHEMA_V3_CHECKSUM = "fa90bc4d0d42331cdbcfea69b68752c23c2aa03d38c956a1bb4449645716624e";
export const HUMAN_MEMORY_SCHEMA_VERSION = "20260719_approval_kind_bindings_v4";
export const HUMAN_MEMORY_SCHEMA_CONTRACT = "agentops-human-session-approval-kind-bindings-contract-v4";
export const HUMAN_MEMORY_SCHEMA_CHECKSUM = "03efa7fe3f5a9e9746e6cd6f8a40f96904c3bb751a460efc587650c08d46849e";
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
  human_approval_decision_requests: {
    workspace_id: { dataType: "text", nullable: false },
    user_id: { dataType: "text", nullable: false },
    idempotency_key_hash: { dataType: "text", nullable: false },
    request_hash: { dataType: "text", nullable: false },
    approval_id: { dataType: "text", nullable: false },
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
  {
    tableName: "human_approval_decision_requests",
    constraintName: "human_approval_decision_requests_pkey",
    constraintType: "p",
    definition: "PRIMARY KEY (workspace_id, user_id, idempotency_key_hash)",
  },
  {
    tableName: "human_approval_decision_requests",
    constraintName: "human_approval_decision_requests_decision_check",
    constraintType: "c",
    definition: "CHECK (decision = ANY (ARRAY['approved'::text, 'rejected'::text]))",
  },
  {
    tableName: "human_approval_decision_requests",
    constraintName: "human_approval_decision_requests_status_check",
    constraintType: "c",
    definition: "CHECK (status = 'completed'::text)",
  },
  {
    tableName: "human_approval_decision_requests",
    constraintName: "human_approval_decision_requests_user_id_fkey",
    constraintType: "f",
    definition: "FOREIGN KEY (user_id) REFERENCES users(user_id)",
  },
  {
    tableName: "human_approval_decision_requests",
    constraintName: "human_approval_decision_requests_approval_id_fkey",
    constraintType: "f",
    definition: "FOREIGN KEY (approval_id) REFERENCES approvals(approval_id)",
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
  {
    tableName: "human_approval_decision_requests",
    indexName: "idx_human_approval_decision_approval",
    unique: false,
    keys: ["workspace_id", "approval_id", "created_at"],
  },
  {
    tableName: "human_approval_decision_requests",
    indexName: "idx_human_approval_decision_idempotency_unique",
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

type ApprovalKindTriggerRow = {
  table_name: string;
  trigger_name: string;
  enabled: string;
  deferrable: boolean;
  initially_deferred: boolean;
  function_name: string;
  definition: string;
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

async function assertApprovalKindBindingsReady(client: PoolClient) {
  let columnRows: Array<ColumnRow & { column_default: string | null }>;
  try {
    const result = await client.query<ColumnRow & { column_default: string | null }>(
      `SELECT table_name,column_name,data_type,is_nullable,column_default
      FROM information_schema.columns
      WHERE table_schema=current_schema()
        AND table_name='approvals' AND column_name='approval_kind'`,
    );
    columnRows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_approval_kind_column_mismatch");
  }
  const column = columnRows[0];
  if (columnRows.length !== 1
    || column.data_type !== "text"
    || column.is_nullable !== "NO"
    || column.column_default !== null) {
    throw new SchemaReadinessError("human_memory_schema_approval_kind_column_mismatch");
  }

  let constraintRows: Array<{ constraint_type: string; validated: boolean; definition: string }>;
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
        AND relation.relname='approvals'
        AND constraint_record.conname='approvals_kind_binding_check'`,
    );
    constraintRows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_approval_kind_constraint_mismatch");
  }
  const kindConstraint = constraintRows[0];
  const kindDefinition = normalizedDefinition(kindConstraint?.definition || "");
  const requiredKindDefinition = normalizedDefinition(
    "CHECK ((approval_kind = ANY (ARRAY['tool_execution'::text, 'prepared_action'::text])) AND tool_call_id IS NOT NULL OR (approval_kind = ANY (ARRAY['run_execution'::text, 'agent_enrollment'::text, 'customer_delivery'::text])) AND tool_call_id IS NULL)",
  );
  if (constraintRows.length !== 1
    || kindConstraint.constraint_type !== "c"
    || !kindConstraint.validated
    || kindDefinition !== requiredKindDefinition) {
    throw new SchemaReadinessError("human_memory_schema_approval_kind_constraint_mismatch");
  }

  let indexRows: IndexRow[];
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
      WHERE namespace.nspname=current_schema()
        AND index_relation.relname='idx_agent_gateway_enrollment_approval_unique'`,
    );
    indexRows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_enrollment_approval_index_mismatch");
  }
  const enrollmentIndex = indexRows[0];
  if (indexRows.length !== 1
    || enrollmentIndex.table_name !== "agent_gateway_enrollment_requests"
    || enrollmentIndex.access_method !== "btree"
    || !enrollmentIndex.is_unique
    || enrollmentIndex.is_primary
    || !enrollmentIndex.is_valid
    || !enrollmentIndex.is_ready
    || enrollmentIndex.included_count !== 0
    || enrollmentIndex.predicate !== null
    || enrollmentIndex.key_definitions.length !== 1
    || enrollmentIndex.key_definitions[0] !== "approval_id") {
    throw new SchemaReadinessError("human_memory_schema_enrollment_approval_index_mismatch");
  }

  let functionRows: Array<{ function_name: string; source: string }>;
  try {
    const result = await client.query<{ function_name: string; source: string }>(
      `SELECT procedure.proname AS function_name,procedure.prosrc AS source
      FROM pg_proc procedure
      JOIN pg_namespace namespace ON namespace.oid=procedure.pronamespace
      WHERE namespace.nspname=current_schema()
        AND procedure.proname=ANY($1::text[])
        AND pg_get_function_identity_arguments(procedure.oid) IN ('', 'target_approval_id text')`,
      [[
        "agentops_assert_approval_kind_binding",
        "agentops_enforce_approval_kind_binding",
        "agentops_enforce_approval_kind_immutable",
        "agentops_enforce_approval_parent_binding_immutable",
        "agentops_enforce_audit_log_append_only",
        "agentops_enforce_customer_delivery_evidence_seal",
      ]],
    );
    functionRows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_approval_kind_functions_mismatch");
  }
  const functions = new Map(functionRows.map((row) => [row.function_name, normalizedDefinition(row.source)]));
  const assertionSource = functions.get("agentops_assert_approval_kind_binding") || "";
  const enforcementSource = functions.get("agentops_enforce_approval_kind_binding") || "";
  const immutableSource = functions.get("agentops_enforce_approval_kind_immutable") || "";
  const parentImmutableSource = functions.get("agentops_enforce_approval_parent_binding_immutable") || "";
  const auditAppendOnlySource = functions.get("agentops_enforce_audit_log_append_only") || "";
  const evidenceSealSource = functions.get("agentops_enforce_customer_delivery_evidence_seal") || "";
  if (functionRows.length !== 6
    || !assertionSource.includes("approval_record.approval_kind='prepared_action'")
    || !assertionSource.includes("approval_record.approval_kind='agent_enrollment'")
    || !assertionSource.includes("approval_record.approval_kind='tool_execution'")
    || !assertionSource.includes("approval_record.approval_kind IN ('run_execution','customer_delivery')")
    || !assertionSource.includes("MESSAGE='approval_kind_binding_orphaned'")
    || !assertionSource.includes("action.workspace_id=approval_record.run_workspace_id")
    || !assertionSource.includes("request.workspace_id=approval_record.run_workspace_id")
    || !assertionSource.includes("approval_record.tool_run_id<>approval_record.run_id")
    || !immutableSource.includes("OLD.approval_kind IS DISTINCT FROM NEW.approval_kind")
    || !immutableSource.includes("MESSAGE='approval_kind_immutable'")
    || !immutableSource.includes("OLD.approval_id IS DISTINCT FROM NEW.approval_id")
    || !immutableSource.includes("OLD.task_id IS DISTINCT FROM NEW.task_id")
    || !immutableSource.includes("OLD.run_id IS DISTINCT FROM NEW.run_id")
    || !immutableSource.includes("OLD.tool_call_id IS DISTINCT FROM NEW.tool_call_id")
    || !immutableSource.includes("OLD.requested_by_agent_id IS DISTINCT FROM NEW.requested_by_agent_id")
    || !immutableSource.includes("MESSAGE='approval_binding_immutable'")
    || !immutableSource.includes("MESSAGE='approval_append_only'")
    || !immutableSource.includes("OLD.decision<>'pending'")
    || !immutableSource.includes("MESSAGE='approval_terminal_immutable'")
    || !immutableSource.includes("MESSAGE='approval_decision_state_invalid'")
    || !parentImmutableSource.includes("TG_TABLE_NAME='tasks'")
    || !parentImmutableSource.includes("TG_TABLE_NAME='runs'")
    || !parentImmutableSource.includes("TG_TABLE_NAME='tool_calls'")
    || !parentImmutableSource.includes("MESSAGE='approval_parent_binding_immutable'")
    || !auditAppendOnlySource.includes("MESSAGE='audit_log_append_only'")
    || !evidenceSealSource.includes("approval.approval_kind='customer_delivery'")
    || !evidenceSealSource.includes("approval_record.decision<>'pending'")
    || !evidenceSealSource.includes("IF TG_OP IN ('UPDATE','DELETE') THEN")
    || !evidenceSealSource.includes("old_target_run_id=NULLIF(old_evidence_record->>'run_id','')")
    || !evidenceSealSource.includes("old_target_task_id=NULLIF(old_evidence_record->>'task_id','')")
    || !evidenceSealSource.includes("IF TG_OP IN ('INSERT','UPDATE') THEN")
    || !evidenceSealSource.includes("new_target_run_id=NULLIF(new_evidence_record->>'run_id','')")
    || !evidenceSealSource.includes("new_target_task_id=NULLIF(new_evidence_record->>'task_id','')")
    || !evidenceSealSource.includes("FOR SHARE OF approval")
    || !evidenceSealSource.includes("MESSAGE='customer_delivery_evidence_sealed'")
    || !enforcementSource.includes("IF TG_OP='DELETE' THEN")
    || !enforcementSource.includes("PERFORM agentops_assert_approval_kind_binding(OLD.approval_id)")
    || !enforcementSource.includes("PERFORM agentops_assert_approval_kind_binding(NEW.approval_id)")
    || !enforcementSource.includes("RETURN OLD")) {
    throw new SchemaReadinessError("human_memory_schema_approval_kind_functions_mismatch");
  }

  const expectedTriggers = new Map([
    ["approvals_kind_binding_enforced", "approvals"],
    ["prepared_actions_kind_binding_enforced", "prepared_actions"],
    ["enrollment_requests_kind_binding_enforced", "agent_gateway_enrollment_requests"],
  ]);
  let triggerRows: ApprovalKindTriggerRow[];
  try {
    const result = await client.query<ApprovalKindTriggerRow>(
      `SELECT relation.relname AS table_name,trigger_record.tgname AS trigger_name,
        trigger_record.tgenabled AS enabled,trigger_record.tgdeferrable AS deferrable,
        trigger_record.tginitdeferred AS initially_deferred,procedure.proname AS function_name,
        pg_get_triggerdef(trigger_record.oid,true) AS definition
      FROM pg_trigger trigger_record
      JOIN pg_class relation ON relation.oid=trigger_record.tgrelid
      JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
      JOIN pg_proc procedure ON procedure.oid=trigger_record.tgfoid
      WHERE namespace.nspname=current_schema()
        AND NOT trigger_record.tgisinternal
        AND trigger_record.tgname=ANY($1::text[])`,
      [[...expectedTriggers.keys()]],
    );
    triggerRows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_approval_kind_triggers_mismatch");
  }
  if (triggerRows.length !== expectedTriggers.size) {
    throw new SchemaReadinessError("human_memory_schema_approval_kind_triggers_mismatch");
  }
  for (const trigger of triggerRows) {
    const expectedTable = expectedTriggers.get(trigger.trigger_name);
    const definition = normalizedDefinition(trigger.definition);
    if (!expectedTable
      || trigger.table_name !== expectedTable
      || trigger.enabled !== "O"
      || !trigger.deferrable
      || !trigger.initially_deferred
      || trigger.function_name !== "agentops_enforce_approval_kind_binding"
      || !definition.includes(`CREATE CONSTRAINT TRIGGER ${trigger.trigger_name}`)
      || !definition.includes(`AFTER INSERT OR DELETE OR UPDATE ON ${expectedTable}`)
      || !definition.includes("DEFERRABLE INITIALLY DEFERRED FOR EACH ROW")
      || !definition.includes("EXECUTE FUNCTION agentops_enforce_approval_kind_binding()")) {
      throw new SchemaReadinessError("human_memory_schema_approval_kind_triggers_mismatch");
    }
  }

  let immutableTriggerRows: Array<{
    table_name: string;
    trigger_name: string;
    enabled: string;
    deferrable: boolean;
    initially_deferred: boolean;
    function_name: string;
    definition: string;
  }>;
  try {
    const result = await client.query<{
      table_name: string;
      trigger_name: string;
      enabled: string;
      deferrable: boolean;
      initially_deferred: boolean;
      function_name: string;
      definition: string;
    }>(
      `SELECT relation.relname AS table_name,trigger_record.tgname AS trigger_name,
        trigger_record.tgenabled AS enabled,trigger_record.tgdeferrable AS deferrable,
        trigger_record.tginitdeferred AS initially_deferred,procedure.proname AS function_name,
        pg_get_triggerdef(trigger_record.oid,true) AS definition
      FROM pg_trigger trigger_record
      JOIN pg_class relation ON relation.oid=trigger_record.tgrelid
      JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
      JOIN pg_proc procedure ON procedure.oid=trigger_record.tgfoid
      WHERE namespace.nspname=current_schema()
        AND NOT trigger_record.tgisinternal
        AND trigger_record.tgname='approvals_kind_immutable'`,
    );
    immutableTriggerRows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_approval_kind_triggers_mismatch");
  }
  const immutableTrigger = immutableTriggerRows[0];
  const immutableDefinition = normalizedDefinition(immutableTrigger?.definition || "");
  if (immutableTriggerRows.length !== 1
    || immutableTrigger.table_name !== "approvals"
    || immutableTrigger.enabled !== "O"
    || immutableTrigger.deferrable
    || immutableTrigger.initially_deferred
    || immutableTrigger.function_name !== "agentops_enforce_approval_kind_immutable"
    || immutableDefinition !== "CREATE TRIGGER approvals_kind_immutable BEFORE DELETE OR UPDATE ON approvals FOR EACH ROW EXECUTE FUNCTION agentops_enforce_approval_kind_immutable()") {
    throw new SchemaReadinessError("human_memory_schema_approval_kind_triggers_mismatch");
  }

  const parentImmutableTriggers = new Map([
    ["tasks_approval_parent_binding_immutable", {
      table: "tasks",
      clause: "BEFORE UPDATE OF task_id, workspace_id ON tasks",
    }],
    ["runs_approval_parent_binding_immutable", {
      table: "runs",
      clause: "BEFORE UPDATE OF run_id, task_id, workspace_id, agent_id ON runs",
    }],
    ["tool_calls_approval_parent_binding_immutable", {
      table: "tool_calls",
      clause: "BEFORE UPDATE OF tool_call_id, run_id, agent_id ON tool_calls",
    }],
  ]);
  let parentImmutableTriggerRows: ApprovalKindTriggerRow[];
  try {
    const result = await client.query<ApprovalKindTriggerRow>(
      `SELECT relation.relname AS table_name,trigger_record.tgname AS trigger_name,
        trigger_record.tgenabled AS enabled,trigger_record.tgdeferrable AS deferrable,
        trigger_record.tginitdeferred AS initially_deferred,procedure.proname AS function_name,
        pg_get_triggerdef(trigger_record.oid,true) AS definition
      FROM pg_trigger trigger_record
      JOIN pg_class relation ON relation.oid=trigger_record.tgrelid
      JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
      JOIN pg_proc procedure ON procedure.oid=trigger_record.tgfoid
      WHERE namespace.nspname=current_schema()
        AND NOT trigger_record.tgisinternal
        AND trigger_record.tgname=ANY($1::text[])`,
      [[...parentImmutableTriggers.keys()]],
    );
    parentImmutableTriggerRows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_approval_parent_triggers_mismatch");
  }
  if (parentImmutableTriggerRows.length !== parentImmutableTriggers.size) {
    throw new SchemaReadinessError("human_memory_schema_approval_parent_triggers_mismatch");
  }
  for (const trigger of parentImmutableTriggerRows) {
    const expected = parentImmutableTriggers.get(trigger.trigger_name);
    const definition = normalizedDefinition(trigger.definition);
    if (!expected
      || trigger.table_name !== expected.table
      || trigger.enabled !== "O"
      || trigger.deferrable
      || trigger.initially_deferred
      || trigger.function_name !== "agentops_enforce_approval_parent_binding_immutable"
      || !definition.includes(expected.clause)
      || !definition.includes("EXECUTE FUNCTION agentops_enforce_approval_parent_binding_immutable()")) {
      throw new SchemaReadinessError("human_memory_schema_approval_parent_triggers_mismatch");
    }
  }

  const evidenceSealTriggers = new Map([
    ["tool_calls_customer_delivery_evidence_sealed", "tool_calls"],
    ["evaluations_customer_delivery_evidence_sealed", "evaluations"],
    ["artifacts_customer_delivery_evidence_sealed", "artifacts"],
    ["manifests_customer_delivery_evidence_sealed", "plan_evidence_manifests"],
    ["agent_plans_customer_delivery_evidence_sealed", "agent_plans"],
  ]);
  let evidenceSealTriggerRows: ApprovalKindTriggerRow[];
  try {
    const result = await client.query<ApprovalKindTriggerRow>(
      `SELECT relation.relname AS table_name,trigger_record.tgname AS trigger_name,
        trigger_record.tgenabled AS enabled,trigger_record.tgdeferrable AS deferrable,
        trigger_record.tginitdeferred AS initially_deferred,procedure.proname AS function_name,
        pg_get_triggerdef(trigger_record.oid,true) AS definition
      FROM pg_trigger trigger_record
      JOIN pg_class relation ON relation.oid=trigger_record.tgrelid
      JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
      JOIN pg_proc procedure ON procedure.oid=trigger_record.tgfoid
      WHERE namespace.nspname=current_schema()
        AND NOT trigger_record.tgisinternal
        AND trigger_record.tgname=ANY($1::text[])`,
      [[...evidenceSealTriggers.keys()]],
    );
    evidenceSealTriggerRows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_delivery_evidence_seal_triggers_mismatch");
  }
  if (evidenceSealTriggerRows.length !== evidenceSealTriggers.size) {
    throw new SchemaReadinessError("human_memory_schema_delivery_evidence_seal_triggers_mismatch");
  }
  for (const trigger of evidenceSealTriggerRows) {
    const expectedTable = evidenceSealTriggers.get(trigger.trigger_name);
    const definition = normalizedDefinition(trigger.definition);
    if (!expectedTable
      || trigger.table_name !== expectedTable
      || trigger.enabled !== "O"
      || trigger.deferrable
      || trigger.initially_deferred
      || trigger.function_name !== "agentops_enforce_customer_delivery_evidence_seal"
      || !definition.includes(`BEFORE INSERT OR DELETE OR UPDATE ON ${expectedTable}`)
      || !definition.includes("EXECUTE FUNCTION agentops_enforce_customer_delivery_evidence_seal()")) {
      throw new SchemaReadinessError("human_memory_schema_delivery_evidence_seal_triggers_mismatch");
    }
  }

  let auditAppendTriggerRows: ApprovalKindTriggerRow[];
  try {
    const result = await client.query<ApprovalKindTriggerRow>(
      `SELECT relation.relname AS table_name,trigger_record.tgname AS trigger_name,
        trigger_record.tgenabled AS enabled,trigger_record.tgdeferrable AS deferrable,
        trigger_record.tginitdeferred AS initially_deferred,procedure.proname AS function_name,
        pg_get_triggerdef(trigger_record.oid,true) AS definition
      FROM pg_trigger trigger_record
      JOIN pg_class relation ON relation.oid=trigger_record.tgrelid
      JOIN pg_namespace namespace ON namespace.oid=relation.relnamespace
      JOIN pg_proc procedure ON procedure.oid=trigger_record.tgfoid
      WHERE namespace.nspname=current_schema()
        AND NOT trigger_record.tgisinternal
        AND trigger_record.tgname='audit_logs_append_only'`,
    );
    auditAppendTriggerRows = result.rows;
  } catch {
    throw new SchemaReadinessError("human_memory_schema_audit_append_trigger_mismatch");
  }
  const auditAppendTrigger = auditAppendTriggerRows[0];
  const auditAppendDefinition = normalizedDefinition(auditAppendTrigger?.definition || "");
  if (auditAppendTriggerRows.length !== 1
    || auditAppendTrigger.table_name !== "audit_logs"
    || auditAppendTrigger.enabled !== "O"
    || auditAppendTrigger.deferrable
    || auditAppendTrigger.initially_deferred
    || auditAppendTrigger.function_name !== "agentops_enforce_audit_log_append_only"
    || auditAppendDefinition !== "CREATE TRIGGER audit_logs_append_only BEFORE DELETE OR UPDATE ON audit_logs FOR EACH ROW EXECUTE FUNCTION agentops_enforce_audit_log_append_only()") {
    throw new SchemaReadinessError("human_memory_schema_audit_append_trigger_mismatch");
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
  await assertApprovalKindBindingsReady(client);
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
