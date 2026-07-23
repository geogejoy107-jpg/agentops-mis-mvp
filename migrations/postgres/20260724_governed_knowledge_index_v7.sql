-- Add the governed Postgres knowledge index required by commercial workers.
-- The index stores bounded summaries and source hashes, never raw prompts,
-- responses, transcripts, credentials, or unbounded source bodies.

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

CREATE TABLE IF NOT EXISTS knowledge_documents (
    doc_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    project_id TEXT,
    access_level TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    scope TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    content_summary TEXT,
    indexed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT knowledge_documents_pkey PRIMARY KEY(doc_id)
);

CREATE TABLE IF NOT EXISTS knowledge_chunks (
    chunk_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    project_id TEXT,
    access_level TEXT NOT NULL,
    path TEXT NOT NULL,
    title TEXT NOT NULL,
    heading TEXT NOT NULL,
    heading_path TEXT NOT NULL,
    heading_level INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    source_hash TEXT NOT NULL,
    content_summary TEXT,
    indexed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT knowledge_chunks_pkey PRIMARY KEY(chunk_id)
);

LOCK TABLE knowledge_documents IN SHARE ROW EXCLUSIVE MODE;
LOCK TABLE knowledge_chunks IN SHARE ROW EXCLUSIVE MODE;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM knowledge_documents document
    WHERE document.doc_id !~ '^[A-Za-z0-9._:-]{1,128}$'
      OR document.workspace_id !~ '^[A-Za-z0-9._:-]{1,128}$'
      OR document.access_level NOT IN ('internal','private')
      OR (
        document.workspace_id='global'
        AND document.access_level<>'internal'
      )
      OR btrim(document.path)=''
      OR length(document.path)>1024
      OR document.path ~ '(^/|(^|/)\.\.(/|$)|\\)'
      OR btrim(document.title)=''
      OR length(document.title)>240
      OR btrim(document.category)=''
      OR length(document.category)>80
      OR document.scope NOT IN ('project','org','base','runbook')
      OR document.source_hash !~ '^[a-f0-9]{64}$'
      OR length(COALESCE(document.content_summary,''))>2000
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='knowledge_document_identity_invalid';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM knowledge_documents
    GROUP BY workspace_id,path
    HAVING COUNT(*)>1
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23505',
      MESSAGE='knowledge_document_path_ambiguous';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM knowledge_chunks chunk
    LEFT JOIN knowledge_documents document
      ON document.doc_id=chunk.doc_id
    WHERE document.doc_id IS NULL
      OR chunk.chunk_id !~ '^[A-Za-z0-9._:-]{1,128}$'
      OR chunk.workspace_id<>document.workspace_id
      OR chunk.project_id IS DISTINCT FROM document.project_id
      OR chunk.access_level<>document.access_level
      OR chunk.path<>document.path
      OR chunk.title<>document.title
      OR chunk.source_hash<>document.source_hash
      OR btrim(chunk.heading)=''
      OR length(chunk.heading)>240
      OR btrim(chunk.heading_path)=''
      OR length(chunk.heading_path)>1200
      OR chunk.heading_level<0
      OR chunk.heading_level>6
      OR chunk.chunk_index<1
      OR length(COALESCE(chunk.content_summary,''))>2000
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23514',
      MESSAGE='knowledge_chunk_binding_invalid';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM knowledge_chunks
    GROUP BY doc_id,chunk_index
    HAVING COUNT(*)>1
  ) THEN
    RAISE EXCEPTION USING
      ERRCODE='23505',
      MESSAGE='knowledge_chunk_index_ambiguous';
  END IF;
END
$$;

ALTER TABLE knowledge_documents
DROP CONSTRAINT IF EXISTS knowledge_documents_path_key;

CREATE UNIQUE INDEX IF NOT EXISTS
idx_knowledge_documents_workspace_path_v7
ON knowledge_documents(workspace_id,path);

CREATE UNIQUE INDEX IF NOT EXISTS
idx_knowledge_documents_binding_v7
ON knowledge_documents(doc_id,workspace_id,path,source_hash);

CREATE UNIQUE INDEX IF NOT EXISTS
idx_knowledge_chunks_document_index_v7
ON knowledge_chunks(doc_id,chunk_index);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='knowledge_documents'::regclass
      AND conname='knowledge_documents_identity_v7_check'
  ) THEN
    ALTER TABLE knowledge_documents
    ADD CONSTRAINT knowledge_documents_identity_v7_check
    CHECK(
      doc_id ~ '^[A-Za-z0-9._:-]{1,128}$'
      AND workspace_id ~ '^[A-Za-z0-9._:-]{1,128}$'
      AND access_level IN ('internal','private')
      AND (
        workspace_id<>'global'
        OR access_level='internal'
      )
      AND NULLIF(btrim(path),'') IS NOT NULL
      AND length(path)<=1024
      AND path !~ '(^/|(^|/)\.\.(/|$)|\\)'
      AND NULLIF(btrim(title),'') IS NOT NULL
      AND length(title)<=240
      AND NULLIF(btrim(category),'') IS NOT NULL
      AND length(category)<=80
      AND scope IN ('project','org','base','runbook')
      AND source_hash ~ '^[a-f0-9]{64}$'
      AND length(COALESCE(content_summary,''))<=2000
    );
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='knowledge_chunks'::regclass
      AND conname='knowledge_chunks_shape_v7_check'
  ) THEN
    ALTER TABLE knowledge_chunks
    ADD CONSTRAINT knowledge_chunks_shape_v7_check
    CHECK(
      chunk_id ~ '^[A-Za-z0-9._:-]{1,128}$'
      AND NULLIF(btrim(heading),'') IS NOT NULL
      AND length(heading)<=240
      AND NULLIF(btrim(heading_path),'') IS NOT NULL
      AND length(heading_path)<=1200
      AND heading_level BETWEEN 0 AND 6
      AND chunk_index>=1
      AND length(COALESCE(content_summary,''))<=2000
    );
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='knowledge_chunks'::regclass
      AND conname='knowledge_chunks_document_binding_v7_fkey'
  ) THEN
    ALTER TABLE knowledge_chunks
    ADD CONSTRAINT knowledge_chunks_document_binding_v7_fkey
    FOREIGN KEY(doc_id,workspace_id,path,source_hash)
    REFERENCES knowledge_documents(doc_id,workspace_id,path,source_hash)
    ON UPDATE RESTRICT
    ON DELETE CASCADE;
  END IF;
END
$$;

ALTER TABLE knowledge_documents
ADD COLUMN IF NOT EXISTS search_document TSVECTOR
GENERATED ALWAYS AS (
  to_tsvector(
    'simple'::regconfig,
    COALESCE(path,'') || ' '
      || COALESCE(title,'') || ' '
      || COALESCE(category,'') || ' '
      || COALESCE(content_summary,'')
  )
) STORED;

ALTER TABLE knowledge_chunks
ADD COLUMN IF NOT EXISTS search_document TSVECTOR
GENERATED ALWAYS AS (
  to_tsvector(
    'simple'::regconfig,
    COALESCE(path,'') || ' '
      || COALESCE(title,'') || ' '
      || COALESCE(heading,'') || ' '
      || COALESCE(heading_path,'') || ' '
      || COALESCE(content_summary,'')
  )
) STORED;

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_visibility_v7
ON knowledge_documents(workspace_id,category,updated_at DESC,doc_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_search_v7
ON knowledge_documents USING GIN(search_document);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_visibility_v7
ON knowledge_chunks(workspace_id,doc_id,chunk_index);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_search_v7
ON knowledge_chunks USING GIN(search_document);
