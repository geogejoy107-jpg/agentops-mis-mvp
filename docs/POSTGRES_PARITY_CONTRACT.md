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
Postgres hashes before a Postgres-backed server route can be accepted. The
seventh layer is the backend selection contract,
`storage_backend_selection_fail_closed_v1`, which keeps SQLite as the explicit
Free Local backend and makes requested Postgres startup fail closed until
enterprise entitlement, DSN, opt-in flag, optional driver, and routable server
adapter support are all proven. The eighth layer is the server HTTP read
contract, `postgres_http_read_parity_v1`, which starts the Python server against
a temporary Postgres database, verifies selected current GET route payloads
against the route read-model contract, and proves writes fail closed while the
Postgres server adapter is still read-only. The ninth layer is the CLI read
contract, `postgres_cli_read_parity_v1`, which drives selected `agentops` CLI
read commands, including Agent Plan and plan-evidence list/get/verify reads,
against that same Postgres-backed read-only server so the machine-facing Agent
Gateway CLI/API contract remains valid beyond the default SQLite backend. The
tenth layer is the write-helper parity contract,
`postgres_write_helper_parity_v1`, which runs selected `server.repo_*` write
helpers against both temporary SQLite and temporary Postgres, compares outcomes
and snapshots, and keeps HTTP/CLI writes fail-closed until a routed write
adapter is explicitly proven. The eleventh layer is the first routed write
contract, `postgres_http_write_task_parity_v1`, which keeps Postgres HTTP
writes blocked by default, then enables only explicit task, execution-start,
agent/run progress and completion heartbeat, evidence, plan, memory-candidate, approval-request, and audit
allowlist routes under `AGENTOPS_POSTGRES_WRITE_HTTP=1`: `POST /api/tasks`,
scoped `POST /api/agent-gateway/tasks`, scoped
`POST /api/agent-gateway/tasks/:task_id/claim`, scoped
`POST /api/agent-gateway/runs/start`, scoped `POST /api/agent-gateway/heartbeat`,
scoped `POST /api/agent-gateway/runs/:run_id/heartbeat`, scoped Gateway
tool/evaluation/artifact evidence, Agent Plan, plan-evidence manifest, memory
proposal, and run/task approval/audit routes. It proves task, run, heartbeat,
completion sync, evidence, plan, memory, approval, runtime event, and audit rows
persist in Postgres while missing scopes, cross-workspace, cross-agent,
same-workspace intruder, terminal run revival, memory overwrite, approval overwrite, and
non-allowlisted writes still fail closed.
The twelfth layer is `postgres_cli_write_parity_v1`, which drives the same
scoped Agent Gateway write lane through actual `agentops` CLI commands against
the Postgres-backed server. It proves read-only CLI writes, missing-scope CLI
writes, and non-allowlisted CLI mutations fail closed, while scoped CLI
commands persist task, claim, run-start, agent/run heartbeat, run completion
heartbeat, tool/evaluation/artifact evidence, Agent Plan, verified
plan-evidence, memory, approval, audit, runtime-event, and token heartbeat
evidence in Postgres without falling back to SQLite.
The thirteenth layer is the BYOC recovery contract,
`postgres_backup_restore_v1`, backed by the mandatory
`postgres_backup_manifest_v1` sidecar. It creates a custom-format `pg_dump`,
verifies its SHA-256 and `pg_restore` table of contents, requires explicit
restore and target-state confirmation, restores into a fresh database, compares
source/restored fixture counts, creates a pre-restore archive before overwrite,
and rejects tampered archives without printing credentials or raw rows.

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
- Preserve SQL string literals containing `%` patterns, such as
  `LIKE '%example%'`, by escaping them for psycopg while keeping the server-side
  SQL semantics unchanged.
- Translate SQLite `INSERT OR IGNORE` helper statements into Postgres
  `ON CONFLICT DO NOTHING` without changing Free Local behavior.
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
python3 scripts/storage_backend_selection_smoke.py
python3 scripts/storage_postgres_http_read_parity_smoke.py
python3 scripts/storage_postgres_cli_read_parity_smoke.py
python3 scripts/storage_postgres_write_helper_parity_smoke.py
python3 scripts/storage_postgres_http_write_task_smoke.py
python3 scripts/storage_postgres_cli_write_parity_smoke.py
python3 scripts/agentops_postgres_backup_smoke.py
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
payloads, produce identical SQLite/Postgres hashes. The seventh command proves
server backend selection is explicit: default SQLite is active through
`/api/storage/backend-status`, while requested Postgres startup fails closed
instead of silently falling back. The eighth command starts the actual server
in `AGENTOPS_STORAGE_BACKEND=postgres` read-only HTTP mode, confirms 14
selected GET routes match the locked read-model hash, and confirms POST writes
return `postgres_read_only_backend` without creating rows. The ninth command
runs selected `agentops` CLI reads, including Agent Plan and plan-evidence
list/get/verify reads, against the same Postgres-backed server and checks a CLI
write command is blocked. The tenth command executes selected `repo_*` write
helpers on SQLite and Postgres, compares helper outcomes and persisted
snapshots, proves chained audit-row dict compatibility and transaction rollback
control, and still does not enable any HTTP/CLI writes. The eleventh command
starts the actual Postgres-backed server twice: first to confirm read-only
HTTP still blocks `POST /api/tasks`, `POST /api/agent-gateway/tasks`, scoped
task claim, run start, tool/evaluation/artifact evidence, Agent Plan,
plan-evidence, memory proposal, approval request, and audit routes, then with
`AGENTOPS_POSTGRES_WRITE_HTTP=1` to create one human/API task and one scoped
Agent Gateway task, claim that task, start one run, write evidence, submit a
plan, verify a plan-evidence manifest, propose a candidate memory, create a
pending approval request, and emit run/task-bound audit through the explicit
allowlist. It reads the task/run back,
proves runtime/audit evidence persisted, rejects missing/absent Gateway tokens,
rejects missing `tasks:create` / `tasks:claim` / `runs:write` /
`memories:propose` / `approvals:request`, rejects body/header cross-workspace,
cross-agent, same-workspace intruder, memory overwrite, approval overwrite,
task/tool/requester mismatch, and task/run mismatch requests, and proves broader
Gateway writes such as knowledge indexing remain blocked. The twelfth command
drives the actual `agentops` CLI against the Postgres write server, confirms
read-only, missing-scope, and non-allowlisted CLI mutations fail closed, then
persists a scoped agent heartbeat, task create/claim, run start/progress
heartbeat, run completion heartbeat, tool/evaluation/artifact evidence, Agent
Plan, verified plan-evidence manifest, memory proposal, approval request, and
audit emit through the CLI. The final command proves the broader current SQLite
helper behavior that Postgres must match.
The Postgres backup command is the Gate 5 data-plane recovery proof. Merely
installing `agentops_postgres_backup.py` or its smoke does not prove that a dump
was restored. Authoritative evidence requires `ok=true`, `skipped=false`,
`contract=postgres_backup_restore_v1`, and
`manifest_contract=postgres_backup_manifest_v1` from the Docker-backed smoke.

When Docker is unavailable on a local machine, use the non-authoritative
diagnostic mode only to keep wider readiness checks moving:

```bash
python3 scripts/storage_postgres_container_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_adapter_contract_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_optional_adapter_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_boundary_parity_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_route_read_model_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_http_read_parity_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_cli_read_parity_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_write_helper_parity_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_http_write_task_smoke.py --skip-if-unavailable
python3 scripts/storage_postgres_cli_write_parity_smoke.py --skip-if-unavailable
python3 scripts/agentops_postgres_backup_smoke.py --skip-if-unavailable
```

This mode reports `skipped: true`; it is not final BYOC/Postgres evidence.

The Postgres recovery utility and its two contracts are implemented, but a
current non-skipped smoke receipt is still required before deployment readiness
or commercial handoff may call recovery accepted.

Current local evidence on `codex/commercial-migration-closed-loop`:

- `postgres_container_parity_v1` passed against `postgres:16-alpine` with
  `postgres_ddl_hash=315c235397dcd9efd1730751e82e8f0110b3ea3a0cf8fa95a2d3c12c045da1eb`.
- `postgres_adapter_sql_contract_v1` passed against `postgres:16-alpine` with
  `fixture_hash=64bcf2f3312c97ff045d52a32a32fd0dbd9a19019f98cec69395e2d13a980491`
  and `free_local_dependencies=[]`.
- `postgres_optional_psycopg_adapter_v1` passed against `postgres:16-alpine`
  with a temporary psycopg target, `free_local_dependencies=[]`, qmark/named
  SQL execution, literal question mark and `LIKE '%...%'` percent-pattern SQL
  literals, dict-like row shape, and zero cross-workspace rows.
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
- `storage_backend_selection_fail_closed_v1` passed locally: default SQLite is
  active through `/api/storage/backend-status`, and requested Postgres startup
  exits before SQLite seed/reset when entitlement, DSN, or opt-in flag is
  missing; Postgres server reads also require
  `AGENTOPS_POSTGRES_READ_ONLY_HTTP=1`.
- `postgres_http_read_parity_v1` passed against `postgres:16-alpine` with a
  temporary psycopg target: server backend mode was `read_only_http`, 14
  selected GET routes matched read-model hash
  `e6a562071962c4e2ff99236e39cfa2ee3b53f36b46c3b0d268507a5ced08f843`,
  POST writes returned `503 postgres_read_only_backend`,
  `free_local_dependencies=[]`, and no fallback to SQLite occurred.
- `postgres_cli_read_parity_v1` passed against `postgres:16-alpine` with a
  temporary psycopg target: 16 selected `agentops` CLI read commands for
  task/run/artifact/approval/memory/workflow-job plus Agent Plan and
  plan-evidence list/get/verify readback succeeded against the Postgres-backed
  `read_only_http` server, CLI write guard was checked,
  `postgres_cli_read_snapshot_hash=97c7e8de76856edb42b34bdc7a3e9be1845f60ee000583d40af3c6864c47ba6a`,
  runtime-only `age_sec` is omitted from the contract hash,
  `free_local_dependencies=[]`, and no fallback to SQLite occurred.
- `postgres_write_helper_parity_v1` passed against `postgres:16-alpine` with a
  temporary psycopg target: 29 selected `server.repo_*` write-helper outcomes
  and snapshots matched SQLite, chained audit append and rollback sentinel were
  verified, `postgres_write_helper_hash=bb601af77f646cd06e885254818dac5a63f3b4f596475be872efe0f7ff560c0b`,
  `free_local_dependencies=[]`, no fallback to SQLite occurred, and HTTP/CLI
  writes remain disabled at this gate.
- `postgres_http_write_task_parity_v1`,
  `postgres_http_gateway_execution_start_write_v1`,
  `postgres_http_gateway_heartbeat_write_v1`,
  `postgres_http_gateway_run_heartbeat_write_v1`,
  `postgres_http_gateway_run_completion_heartbeat_write_v1`,
  `postgres_http_gateway_evidence_write_v1`,
  `postgres_http_gateway_plan_evidence_write_v1`,
  `postgres_http_gateway_approval_write_v1`,
  `postgres_http_gateway_audit_write_v1`, and
  `postgres_http_gateway_memory_write_v1`,
  `postgres_http_runtime_prepared_action_write_v1`, and
  `postgres_http_runtime_approval_decision_write_v1` passed against `postgres:16-alpine`
  with a temporary psycopg target: read-only mode still returned
  `503 postgres_read_only_backend` for `POST /api/tasks` and
  scoped Agent Gateway task create/claim/run-start/tool/evaluation/artifact/
  heartbeat/Agent Plan/plan-evidence/memory/approval/audit plus fixed
  Hermes/OpenClaw runtime prepared-action routes; explicit
  `AGENTOPS_POSTGRES_WRITE_HTTP=1` mode allowed only those task,
  execution-start, heartbeat, execution-evidence, plan-evidence,
  memory-candidate, approval-request, and run/task-bound audit routes, created
  `tsk_pg_http_write_task` and scoped Gateway task `tsk_pg_gateway_write_task`,
  claimed the Gateway task, started `run_pg_gateway_write_start`, updated agent
  heartbeat state and token `last_heartbeat_at`, wrote a run heartbeat for
  `run_pg_gateway_write_start`, completed `run_pg_gateway_completion_heartbeat`
  through run heartbeat and verified task completion plus agent idle sync, wrote
  `tc_pg_gateway_write_evidence`, `eval_pg_gateway_write_evidence`, and
  `art_pg_gateway_write_evidence`, created `plan_pg_gateway_write`, submitted
  verified manifest `pem_pg_gateway_write`, proposed candidate memory
  `mem_pg_gateway_write`, created pending approval `ap_pg_gateway_write`, moved
  the run/task to `waiting_approval`, emitted run-bound audit action
  `agent_gateway.postgres_audit_write`, read task and run back through HTTP,
  persisted runtime/audit rows in Postgres, rejected absent Gateway token at
  `401`, rejected missing `agents:heartbeat`, missing `tasks:create`, missing
  `tasks:claim`, missing `runs:write`, missing `toolcalls:write`, missing `evaluations:submit`,
  missing `artifacts:write`, missing `agent_plans:write`, missing
  `plan_evidence:write`, missing `memories:propose`, missing
  `approvals:request`, and missing `audit:write` at `403`, rejected body/header
  cross-workspace, cross-agent, same-workspace intruder, run heartbeat task
  mismatch, terminal run revival, manifest task/run binding mismatch,
  memory task/run mismatch, approved/cross-workspace/other-agent
  memory overwrite, approval task/tool/requester mismatch, approved approval
  overwrite, audit task/run mismatch, and intruder audit without `run_id`
  Gateway requests at `403`, kept `POST /api/agent-gateway/knowledge/index` and
  `POST /api/agents` blocked at `503`, proved fixed OpenClaw and Hermes prepare
  -> premature resume blocked -> row-gated approve -> hash mismatch blocked ->
  exact resume consumed -> replay blocked with provider call count exactly one,
  kept non-prepared approval decisions blocked at `503`, exposed the same
  contract through `storage_backend_status.runtime_write_gate` for CLI/API/Next
  deployment readback, kept `free_local_dependencies=[]`, and
  did not fall back to SQLite.
- `nextjs_deployment_postgres_runtime_write_fixture_v1` passed against a
  temporary Postgres-backed MIS API in `experimental_write_http` mode and a
  Next.js server pointed at it. The browser fixture proves
  `/workspace/deployment` renders `runtime_write_gate=active`, the fixed
  OpenClaw/Hermes prepared-action contracts, exact-resume and row-gated approval
  proofs, all three fixed write routes, and the non-fixed runtime write block;
  it also confirms the Next proxy cannot mutate read-only ledger tables while
  rendering the deployment page.
- `deployment_readiness_postgres_runtime_write_fixture_v1` passed against a
  temporary Postgres-backed MIS API in `experimental_write_http` mode. The
  backend fixture proves `GET /api/deployment/readiness` and
  `agentops deployment readiness` expose the active fixed runtime write gate,
  all three fixed write routes, exact-resume and row-gated approval proofs,
  non-allowlisted writes blocked at `503`, token omission, no SQLite fallback,
  and unchanged Postgres ledger counts.
- `byoc_deployment_acceptance_v1` handoff mode now runs
  `python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture`
  so recovery/export acceptance is paired with the backend Postgres
  `deployment_readiness_postgres_runtime_write_fixture_v1` proof before BYOC
  handoff.
- `postgres_cli_write_parity_v1`,
  `postgres_cli_gateway_task_write_v1`,
  `postgres_cli_gateway_execution_start_write_v1`,
  `postgres_cli_gateway_heartbeat_write_v1`,
  `postgres_cli_gateway_run_heartbeat_write_v1`,
  `postgres_cli_gateway_run_completion_heartbeat_write_v1`,
  `postgres_cli_gateway_evidence_write_v1`,
  `postgres_cli_gateway_plan_evidence_write_v1`,
  `postgres_cli_gateway_memory_write_v1`,
  `postgres_cli_gateway_approval_write_v1`, and
  `postgres_cli_gateway_audit_write_v1` passed against `postgres:16-alpine`
  with a temporary psycopg target: actual `agentops` CLI commands wrote agent
  heartbeat, task create/claim, run start/progress heartbeat, tool call,
  evaluation, artifact, Agent Plan, verified plan-evidence manifest, memory
  candidate, audit event, pending approval request, and a separate completion
  heartbeat that set the run completed, task completed, and agent idle. The
  smoke also verified read-only CLI task create, missing `tasks:create`, and
  CLI knowledge index mutations fail closed, token `last_used_at` and
  `last_heartbeat_at` are recorded, `free_local_dependencies=[]`, no token-like
  values leak, and no fallback to SQLite occurred.
- Source install packaging includes `agentops_mis_storage.postgres`; importing
  the module and translating SQL does not require psycopg.

## Next Gate

Postgres parity is not complete until the adapter boundary:

- routes more `repo_*` helper flows through the same shared fixture pattern;
- proves Postgres write helpers before widening any routed Postgres write
  routes beyond the explicit task/execution/evidence/plan/memory/approval/audit
  write allowlist;
- keeps write routes disabled until an explicit routed write-adapter smoke
  proves the small route surface that will be enabled;
- keeps backend selection fail-closed so Postgres configuration cannot silently
  run against SQLite;
- keeps qmark/named placeholder translation and literal `?` behavior locked;
- keeps psycopg optional and outside Free Local dependencies;
- verifies no raw prompts, raw responses, secrets, generated caches, local DBs,
  or private transcripts are written.
