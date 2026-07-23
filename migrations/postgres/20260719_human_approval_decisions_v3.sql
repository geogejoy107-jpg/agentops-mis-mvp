-- Add durable request identity for Human Session approval decisions. The
-- migration runner owns the surrounding transaction and exact receipt.

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

CREATE TABLE IF NOT EXISTS human_approval_decision_requests (
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    idempotency_key_hash TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    CONSTRAINT human_approval_decision_requests_pkey PRIMARY KEY(workspace_id,user_id,idempotency_key_hash),
    CONSTRAINT human_approval_decision_requests_decision_check CHECK(decision IN ('approved','rejected')),
    CONSTRAINT human_approval_decision_requests_status_check CHECK(status IN ('completed')),
    CONSTRAINT human_approval_decision_requests_user_id_fkey FOREIGN KEY(user_id) REFERENCES users(user_id),
    CONSTRAINT human_approval_decision_requests_approval_id_fkey FOREIGN KEY(approval_id) REFERENCES approvals(approval_id)
);

CREATE INDEX IF NOT EXISTS idx_human_approval_decision_approval
ON human_approval_decision_requests(workspace_id,approval_id,created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_human_approval_decision_idempotency_unique
ON human_approval_decision_requests(workspace_id,user_id,idempotency_key_hash);
