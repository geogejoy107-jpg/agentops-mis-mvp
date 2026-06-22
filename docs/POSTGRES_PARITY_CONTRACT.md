# Postgres Parity Contract

## Purpose

Gate 3 moves AgentOps MIS toward Enterprise/BYOC storage without breaking Free
Local. SQLite remains the executable local ledger until Postgres has proven the
same helper contract with the same response shapes, redaction behavior, and
workspace isolation.

This contract is the pre-container parity layer. Its machine-readable contract
ID is `postgres_parity_pre_container_v1`. It is intentionally derived from
`server.SCHEMA_SQL`, because `server.py` is still the executable schema
authority for the dependency-free local product line.

## Contract v1

The first Postgres adapter must preserve these invariants:

- Keep current HTTP and CLI response shapes unchanged.
- Keep JSON-like fields as text in the first adapter pass; callers already
  serialize and parse these fields explicitly.
- Keep boolean flags as integer-compatible values until response parity is
  verified.
- Preserve workspace filters and cross-workspace exclusion for task, run,
  memory, approval, evaluation, artifact, audit, workflow job, Agent Gateway,
  Agent Plan, plan-evidence, and prepared-action helpers.
- Preserve approval/prepared-action exact-resume fields:
  `normalized_args_json`, `args_hash`, `snapshot_ref`, `snapshot_hash`,
  `status`, `approved_at`, `consumed_at`, and `result_json`.
- Translate DB-API `?` placeholders into Postgres `$1`, `$2`, ... placeholders
  without touching literal question marks inside SQL strings.
- Exclude SQLite-only runtime features from Postgres DDL generation, including
  PRAGMA and FTS5 virtual tables.

## Locked Tables

`python3 scripts/storage_postgres_contract_smoke.py` requires the executable
schema to include:

- core ledger: `users`, `agents`, `tasks`, `runs`, `tool_calls`, `approvals`,
  `evaluations`, `artifacts`, `audit_logs`, `memories`;
- prepared actions: `prepared_actions`;
- runtime and workflow state: `runtime_connectors`, `runtime_events`,
  `workflow_jobs`;
- Agent Gateway credentials and sessions: `agent_gateway_tokens`,
  `agent_gateway_sessions`, `agent_gateway_enrollment_requests`;
- planning evidence: `agent_plans`, `plan_evidence_manifests`;
- knowledge metadata: `knowledge_documents`.

## Verification

Current pre-container proof:

```bash
python3 scripts/storage_postgres_contract_smoke.py
python3 scripts/storage_boundary_sqlite_smoke.py
```

The first command validates the Postgres DDL contract derived from
`server.SCHEMA_SQL`. The second command proves the current SQLite helper
behavior that Postgres must match.

## Next Gate

Postgres parity is not complete until a container-backed smoke:

- creates the generated Postgres schema;
- runs the storage-boundary fixture against a Postgres adapter;
- proves identical create/read/update/filter outcomes for the locked helper
  set;
- proves cross-workspace exclusion;
- verifies no raw prompts, raw responses, secrets, generated caches, local DBs,
  or private transcripts are written.
