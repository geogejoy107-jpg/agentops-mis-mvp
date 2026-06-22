# Postgres Parity Contract

## Purpose

Gate 3 moves AgentOps MIS toward Enterprise/BYOC storage without breaking Free
Local. SQLite remains the executable local ledger until Postgres has proven the
same helper contract with the same response shapes, redaction behavior, and
workspace isolation.

The first layer is the pre-container parity contract. Its machine-readable
contract ID is `postgres_parity_pre_container_v1`. The second layer is the
container parity contract, `postgres_container_parity_v1`, which proves the
generated DDL and representative storage-boundary fixture inside a real
Postgres container before a Python Postgres adapter is accepted. The third
layer is the adapter SQL contract, `postgres_adapter_sql_contract_v1`, which
locks SQLite helper placeholder translation and proves representative
insert/update/select helper SQL inside Postgres while keeping psycopg optional.

Both layers are intentionally derived from `server.SCHEMA_SQL`, because
`server.py` is still the executable schema authority for the dependency-free
local product line.

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

Gate 3 proof commands:

```bash
python3 scripts/storage_postgres_contract_smoke.py
python3 scripts/storage_postgres_container_smoke.py
python3 scripts/storage_postgres_adapter_contract_smoke.py
python3 scripts/storage_boundary_sqlite_smoke.py
```

The first command validates the Postgres DDL contract derived from
`server.SCHEMA_SQL`. The second command starts a temporary Postgres container,
creates the generated schema, inserts representative task/run/tool/approval/
prepared-action/plan-evidence rows, and proves workspace isolation plus parity
indexes. The third command translates representative SQLite helper SQL into
psycopg-compatible parameter forms, executes rendered helper SQL inside
Postgres, and verifies Free Local still has no required psycopg dependency. The
fourth command proves the current SQLite helper behavior that Postgres must
match.

When Docker is unavailable on a local machine, use the non-authoritative
diagnostic mode only to keep wider readiness checks moving:

```bash
python3 scripts/storage_postgres_container_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_adapter_contract_smoke.py --skip-if-unavailable
```

This mode reports `skipped: true`; it is not final BYOC/Postgres evidence.

Current local evidence on `codex/commercial-migration-closed-loop`:

- `postgres_container_parity_v1` passed against `postgres:16-alpine` with
  `postgres_ddl_hash=315c235397dcd9efd1730751e82e8f0110b3ea3a0cf8fa95a2d3c12c045da1eb`.
- `postgres_adapter_sql_contract_v1` passed against `postgres:16-alpine` with
  `fixture_hash=64bcf2f3312c97ff045d52a32a32fd0dbd9a19019f98cec69395e2d13a980491`
  and `free_local_dependencies=[]`.

## Next Gate

Postgres parity is not complete until the container-backed smoke:

- creates the generated Postgres schema;
- runs the storage-boundary fixture against a Postgres adapter;
- proves identical create/read/update/filter outcomes for the locked helper
  set;
- proves cross-workspace exclusion;
- proves representative Python adapter SQL translation for qmark and named
  placeholders without adding required Free Local dependencies;
- verifies no raw prompts, raw responses, secrets, generated caches, local DBs,
  or private transcripts are written.
