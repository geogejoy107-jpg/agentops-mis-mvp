-- Bind commercial RuntimeEvent and Memory evidence to an explicit workspace.
-- Ambiguous historical evidence fails migration instead of being assigned to a
-- guessed tenant.

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

LOCK TABLE tasks IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE runs IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE memories IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE runtime_events IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS workspace_id TEXT;

ALTER TABLE memories
ADD COLUMN IF NOT EXISTS run_id TEXT;

ALTER TABLE runtime_events
ADD COLUMN IF NOT EXISTS workspace_id TEXT;

UPDATE runtime_events event
SET workspace_id=run.workspace_id
FROM runs run
WHERE event.workspace_id IS NULL
  AND event.run_id=run.run_id;

UPDATE runtime_events event
SET workspace_id=task.workspace_id
FROM tasks task
WHERE event.workspace_id IS NULL
  AND event.task_id=task.task_id;

UPDATE runtime_events
SET workspace_id='global'
WHERE workspace_id IS NULL
  AND run_id IS NULL
  AND task_id IS NULL
  AND agent_id IS NULL;

UPDATE memories memory
SET run_id=run.run_id
FROM runs run
WHERE memory.run_id IS NULL
  AND memory.source_type='run_log'
  AND memory.source_ref=run.run_id;

UPDATE memories memory
SET workspace_id=run.workspace_id
FROM runs run
WHERE memory.workspace_id IS NULL
  AND memory.run_id=run.run_id;

UPDATE memories memory
SET workspace_id=task.workspace_id
FROM tasks task
WHERE memory.workspace_id IS NULL
  AND memory.task_id=task.task_id;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM runtime_events event
    LEFT JOIN runs run
      ON run.run_id=event.run_id
    LEFT JOIN tasks task
      ON task.task_id=event.task_id
    WHERE event.workspace_id IS NULL
      OR event.workspace_id !~ '^[A-Za-z0-9._:-]{1,128}$'
      OR (
        event.run_id IS NOT NULL
        AND (
          run.run_id IS NULL
          OR run.workspace_id<>event.workspace_id
          OR event.task_id IS DISTINCT FROM run.task_id
          OR event.agent_id IS DISTINCT FROM run.agent_id
        )
      )
      OR (
        event.task_id IS NOT NULL
        AND (
          task.task_id IS NULL
          OR task.workspace_id<>event.workspace_id
        )
      )
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='runtime_event_workspace_binding_ambiguous';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM memories memory
    LEFT JOIN runs run
      ON run.run_id=memory.run_id
    LEFT JOIN tasks task
      ON task.task_id=memory.task_id
    WHERE memory.workspace_id IS NULL
      OR memory.workspace_id !~ '^[A-Za-z0-9._:-]{1,128}$'
      OR (
        memory.run_id IS NOT NULL
        AND (
          run.run_id IS NULL
          OR run.workspace_id<>memory.workspace_id
          OR memory.task_id IS DISTINCT FROM run.task_id
          OR memory.agent_id IS DISTINCT FROM run.agent_id
        )
      )
      OR (
        memory.task_id IS NOT NULL
        AND (
          task.task_id IS NULL
          OR task.workspace_id<>memory.workspace_id
        )
      )
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='memory_workspace_binding_ambiguous';
  END IF;
END
$$;

ALTER TABLE memories
ALTER COLUMN workspace_id SET NOT NULL;

ALTER TABLE runtime_events
ALTER COLUMN workspace_id SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='memories'::regclass
      AND conname='memories_workspace_id_v8_check'
  ) THEN
    ALTER TABLE memories
    ADD CONSTRAINT memories_workspace_id_v8_check
    CHECK(workspace_id ~ '^[A-Za-z0-9._:-]{1,128}$');
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='memories'::regclass
      AND conname='memories_run_id_v8_fkey'
  ) THEN
    ALTER TABLE memories
    ADD CONSTRAINT memories_run_id_v8_fkey
    FOREIGN KEY(run_id) REFERENCES runs(run_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='runtime_events'::regclass
      AND conname='runtime_events_workspace_id_v8_check'
  ) THEN
    ALTER TABLE runtime_events
    ADD CONSTRAINT runtime_events_workspace_id_v8_check
    CHECK(workspace_id ~ '^[A-Za-z0-9._:-]{1,128}$');
  END IF;
END
$$;

CREATE OR REPLACE FUNCTION agentops_enforce_worker_evidence_workspace_v8()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  run_row runs%ROWTYPE;
  task_row tasks%ROWTYPE;
BEGIN
  IF NEW.workspace_id !~ '^[A-Za-z0-9._:-]{1,128}$' THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='worker_evidence_workspace_invalid';
  END IF;

  IF NEW.run_id IS NOT NULL THEN
    SELECT * INTO run_row
    FROM runs
    WHERE run_id=NEW.run_id;
    IF NOT FOUND
      OR run_row.workspace_id<>NEW.workspace_id
      OR NEW.task_id IS DISTINCT FROM run_row.task_id
      OR NEW.agent_id IS DISTINCT FROM run_row.agent_id
    THEN
      RAISE EXCEPTION USING
        ERRCODE='23514',
        MESSAGE='worker_evidence_run_binding_invalid';
    END IF;
  END IF;

  IF NEW.task_id IS NOT NULL THEN
    SELECT * INTO task_row
    FROM tasks
    WHERE task_id=NEW.task_id;
    IF NOT FOUND OR task_row.workspace_id<>NEW.workspace_id THEN
      RAISE EXCEPTION USING
        ERRCODE='23514',
        MESSAGE='worker_evidence_task_binding_invalid';
    END IF;
  END IF;

  RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION agentops_reject_runtime_event_mutation_v8()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION USING
    ERRCODE='55000',
    MESSAGE='runtime_event_append_only';
END
$$;

DROP TRIGGER IF EXISTS memories_workspace_binding_v8
ON memories;
CREATE TRIGGER memories_workspace_binding_v8
BEFORE INSERT OR UPDATE ON memories
FOR EACH ROW
EXECUTE FUNCTION agentops_enforce_worker_evidence_workspace_v8();

DROP TRIGGER IF EXISTS runtime_events_workspace_binding_v8
ON runtime_events;
CREATE TRIGGER runtime_events_workspace_binding_v8
BEFORE INSERT ON runtime_events
FOR EACH ROW
EXECUTE FUNCTION agentops_enforce_worker_evidence_workspace_v8();

DROP TRIGGER IF EXISTS runtime_events_append_only_v8
ON runtime_events;
CREATE TRIGGER runtime_events_append_only_v8
BEFORE UPDATE OR DELETE ON runtime_events
FOR EACH ROW
EXECUTE FUNCTION agentops_reject_runtime_event_mutation_v8();

CREATE INDEX IF NOT EXISTS idx_memories_workspace_review_v8
ON memories(workspace_id,review_status,created_at DESC,memory_id);

CREATE INDEX IF NOT EXISTS idx_memories_workspace_run_v8
ON memories(workspace_id,run_id,created_at DESC,memory_id);

CREATE INDEX IF NOT EXISTS idx_runtime_events_workspace_run_v8
ON runtime_events(workspace_id,run_id,created_at DESC,runtime_event_id);
