CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_workspace_created
ON audit_logs(workspace_id,created_at DESC,audit_id DESC);
