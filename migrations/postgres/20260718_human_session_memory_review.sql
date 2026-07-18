-- The TypeScript migration runner owns the transaction and writes the exact
-- component/version/contract/checksum receipt after this structure is verified.

CREATE TABLE IF NOT EXISTS agentops_schema_migrations (
    component TEXT NOT NULL,
    version TEXT NOT NULL,
    schema_contract TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    CONSTRAINT agentops_schema_migrations_pkey PRIMARY KEY(component),
    CONSTRAINT agentops_schema_migrations_checksum_check CHECK(checksum ~ '^[a-f0-9]{64}$')
);

CREATE TABLE IF NOT EXISTS workspace_memberships (
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT workspace_memberships_pkey PRIMARY KEY(workspace_id,user_id),
    CONSTRAINT workspace_memberships_role_check CHECK(role IN ('viewer','operator','approver','owner')),
    CONSTRAINT workspace_memberships_status_check CHECK(status IN ('active','disabled')),
    CONSTRAINT workspace_memberships_user_id_fkey FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS human_login_credentials (
    credential_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    password_params_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT,
    CONSTRAINT human_login_credentials_pkey PRIMARY KEY(credential_id),
    CONSTRAINT human_login_credentials_user_id_key UNIQUE(user_id),
    CONSTRAINT human_login_credentials_username_key UNIQUE(username),
    CONSTRAINT human_login_credentials_username_check CHECK(username=lower(username)),
    CONSTRAINT human_login_credentials_status_check CHECK(status IN ('active','disabled')),
    CONSTRAINT human_login_credentials_user_id_fkey FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS human_sessions (
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    session_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT,
    revoked_at TEXT,
    CONSTRAINT human_sessions_pkey PRIMARY KEY(session_id),
    CONSTRAINT human_sessions_session_hash_key UNIQUE(session_hash),
    CONSTRAINT human_sessions_status_check CHECK(status IN ('active','revoked','expired')),
    CONSTRAINT human_sessions_user_id_fkey FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS human_login_throttle (
    bucket_key TEXT NOT NULL,
    failure_count INTEGER NOT NULL DEFAULT 0,
    window_started_at TEXT NOT NULL,
    blocked_until TEXT,
    updated_at TEXT NOT NULL,
    CONSTRAINT human_login_throttle_pkey PRIMARY KEY(bucket_key),
    CONSTRAINT human_login_throttle_failure_count_check CHECK(failure_count >= 0)
);

CREATE TABLE IF NOT EXISTS human_memory_review_requests (
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    idempotency_key_hash TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    CONSTRAINT human_memory_review_requests_pkey PRIMARY KEY(workspace_id,user_id,idempotency_key_hash),
    CONSTRAINT human_memory_review_requests_decision_check CHECK(decision IN ('approved','rejected')),
    CONSTRAINT human_memory_review_requests_status_check CHECK(status IN ('completed')),
    CONSTRAINT human_memory_review_requests_user_id_fkey FOREIGN KEY(user_id) REFERENCES users(user_id),
    CONSTRAINT human_memory_review_requests_memory_id_fkey FOREIGN KEY(memory_id) REFERENCES memories(memory_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_memberships_user
ON workspace_memberships(user_id,status,workspace_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_memberships_identity_unique
ON workspace_memberships(workspace_id,user_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_human_login_credentials_user_unique
ON human_login_credentials(user_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_human_login_credentials_username_unique
ON human_login_credentials(username);

CREATE UNIQUE INDEX IF NOT EXISTS idx_human_sessions_hash_unique
ON human_sessions(session_hash);

CREATE INDEX IF NOT EXISTS idx_human_sessions_user
ON human_sessions(user_id,status,expires_at);

CREATE INDEX IF NOT EXISTS idx_human_memory_review_memory
ON human_memory_review_requests(workspace_id,memory_id,created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_human_memory_review_idempotency_unique
ON human_memory_review_requests(workspace_id,user_id,idempotency_key_hash);
