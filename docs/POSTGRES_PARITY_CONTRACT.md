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
The fourth layer is the optional driver contract,
`postgres_optional_psycopg_adapter_v1`, which proves the reusable
`agentops_mis_storage.postgres` adapter against a real Postgres container using
a temporary psycopg installation outside the Free Local dependency set.
`agentops_mis_storage.postgres` must remain importable without psycopg so
standard Free Local installs keep working. The fifth layer is the shared
boundary fixture contract, `postgres_boundary_fixture_parity_v1`, which runs
the same Python fixture through SQLite and the optional Postgres adapter, then
compares normalized snapshots. The sixth layer is the route read-model
contract, `postgres_route_read_model_parity_v1`, which projects the same
fixture into selected current HTTP response shapes and compares SQLite and
Postgres hashes before a Postgres-backed server route can be accepted.

All layers are intentionally derived from `server.SCHEMA_SQL`, because
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
python3 scripts/storage_postgres_optional_adapter_smoke.py
python3 scripts/storage_postgres_boundary_parity_smoke.py
python3 scripts/storage_postgres_route_read_model_smoke.py
python3 scripts/storage_boundary_sqlite_smoke.py
```

The first command validates the Postgres DDL contract derived from
`server.SCHEMA_SQL`. The second command starts a temporary Postgres container,
creates the generated schema, inserts representative task/run/tool/approval/
prepared-action/plan-evidence rows, and proves workspace isolation plus parity
indexes. The third command translates representative SQLite helper SQL into
psycopg-compatible parameter forms, executes rendered helper SQL inside
Postgres, and verifies Free Local still has no required psycopg dependency. The
fourth command uses the optional psycopg-backed adapter module to execute schema
and representative helper SQL against a real Postgres container while keeping
driver installation in a temporary target. The fifth command proves the current
SQLite helper behavior can be replayed through the same shared fixture against
SQLite and Postgres with identical snapshots. The sixth command verifies
selected current route read models, including task/run details, run graph,
tool-call, approval, memory, evaluation, artifact, audit, and workflow job
payloads, produce identical SQLite/Postgres hashes. The final command proves
the broader current SQLite helper behavior that Postgres must match.

When Docker is unavailable on a local machine, use the non-authoritative
diagnostic mode only to keep wider readiness checks moving:

```bash
python3 scripts/storage_postgres_container_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_adapter_contract_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_optional_adapter_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_boundary_parity_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_route_read_model_smoke.py --skip-if-unavailable
```

This mode reports `skipped: true`; it is not final BYOC/Postgres evidence.

Current local evidence on `codex/commercial-migration-closed-loop`:

- `postgres_container_parity_v1` passed against `postgres:16-alpine` with
  `postgres_ddl_hash=315c235397dcd9efd1730751e82e8f0110b3ea3a0cf8fa95a2d3c12c045da1eb`.
- `postgres_adapter_sql_contract_v1` passed against `postgres:16-alpine` with
  `fixture_hash=64bcf2f3312c97ff045d52a32a32fd0dbd9a19019f98cec69395e2d13a980491`
  and `free_local_dependencies=[]`.
- `postgres_optional_psycopg_adapter_v1` passed against `postgres:16-alpine`
  with a temporary psycopg target, `free_local_dependencies=[]`, qmark/named
  SQL execution, dict-like row shape, and zero cross-workspace rows.
- `postgres_boundary_fixture_parity_v1` passed against `postgres:16-alpine`
  with shared fixture `storage_boundary_shared_fixture_v1`, identical SQLite
  and Postgres snapshot hash
  `7dcff5f12e7ec4e9fccae0fa92d941c78e95ac1e98e2a14d6f1a7f0de493dd1f`,
  `free_local_dependencies=[]`, and zero cross-workspace leakage.
- `postgres_route_read_model_parity_v1` passed against `postgres:16-alpine`
  across 14 selected route-shaped read models with identical SQLite and
  Postgres read-model hash
  `e6a562071962c4e2ff99236e39cfa2ee3b53f36b46c3b0d268507a5ced08f843`,
  `free_local_dependencies=[]`, and token omission proof.
- Source install packaging includes `agentops_mis_storage.postgres`; importing
  the module and translating SQL does not require psycopg.

## Next Gate

Postgres parity is not complete until the adapter boundary:

- routes more `repo_*` helper flows through the same shared fixture pattern;
- runs selected HTTP/CLI requests against a Postgres-backed server adapter once
  the server can switch storage backends;
- keeps qmark/named placeholder translation and literal `?` behavior locked;
- keeps psycopg optional and outside Free Local dependencies;
- verifies no raw prompts, raw responses, secrets, generated caches, local DBs,
  or private transcripts are written.
