-- Add a structured tenant binding for commercial audit reads. Existing rows
-- remain unscoped unless a later, independently verified backfill owns them.

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE audit_logs
ADD COLUMN IF NOT EXISTS workspace_id TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid = 'audit_logs'::regclass
      AND conname = 'audit_logs_workspace_metadata_match'
  ) THEN
    ALTER TABLE audit_logs
    ADD CONSTRAINT audit_logs_workspace_metadata_match
    CHECK (
      CASE
        WHEN workspace_id IS NULL THEN TRUE
        ELSE metadata_json IS NOT NULL
          AND jsonb_typeof(metadata_json::jsonb) = 'object'
          AND metadata_json::jsonb ->> 'workspace_id' = workspace_id
      END
    ) NOT VALID;
  END IF;
END
$$;

ALTER TABLE audit_logs
VALIDATE CONSTRAINT audit_logs_workspace_metadata_match;
