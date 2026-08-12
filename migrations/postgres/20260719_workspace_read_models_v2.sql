-- Add the structured workspace binding required for commercial audit reads.
-- Existing rows remain unscoped unless an independently verified backfill owns
-- them. The former online-index fragment is intentionally part of this
-- first-party migration so bootstrap has one explicit ordered v2 artifact.

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE audit_logs
ADD COLUMN IF NOT EXISTS workspace_id TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='audit_logs'::regclass
      AND conname='audit_logs_workspace_metadata_match'
  ) THEN
    ALTER TABLE audit_logs
    ADD CONSTRAINT audit_logs_workspace_metadata_match
    CHECK (
      CASE
        WHEN workspace_id IS NULL THEN TRUE
        ELSE metadata_json IS NOT NULL
          AND jsonb_typeof(metadata_json::jsonb)='object'
          AND metadata_json::jsonb ->> 'workspace_id'=workspace_id
      END
    ) NOT VALID;
  END IF;
END
$$;

ALTER TABLE audit_logs
VALIDATE CONSTRAINT audit_logs_workspace_metadata_match;

CREATE INDEX IF NOT EXISTS idx_audit_logs_workspace_created
ON audit_logs(workspace_id,created_at DESC,audit_id DESC);
