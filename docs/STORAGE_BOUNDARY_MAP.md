# Storage Boundary Map

## Purpose

Gate 3 prepares Postgres parity without forking product logic or replacing the
working Python/SQLite product line. SQLite remains canonical until each migrated
flow is covered by an isolated helper-level smoke test.

## Current Boundary

The first storage-boundary slice covers workspace-scoped ledger reads used by
human/admin APIs:

| Flow | Helper boundary | Current caller | SQLite behavior locked by |
| --- | --- | --- | --- |
| Task list/detail | `repo_list_workspace_tasks`, `repo_get_workspace_task`, `repo_task_detail` | `GET /api/tasks`, `GET /api/tasks/:id` | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Run list/detail/export | `repo_list_workspace_runs`, `repo_get_workspace_run`, `repo_run_detail` | `GET /api/runs`, `GET /api/runs/export`, `GET /api/runs/:id` | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Memory list/export/review lookup | `repo_list_workspace_memories`, `repo_get_workspace_memory` | `GET /api/memories`, `GET /api/memories/export`, memory approve/reject | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Approval/evaluation/artifact lists | `repo_list_workspace_approvals`, `repo_list_workspace_evaluations`, `repo_list_workspace_artifacts` | `GET /api/approvals`, `GET /api/evaluations`, `GET /api/artifacts` | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Audit list | `repo_list_workspace_audit` | `GET /api/audit` | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Workflow job list/detail/stuck recovery | `repo_list_workspace_workflow_jobs`, `repo_get_workspace_workflow_job`, `repo_list_workspace_stuck_workflow_jobs` | `GET /api/workflows/jobs`, `GET /api/workflows/jobs/:job_id`, `GET /api/workflows/jobs/stuck`, mark-failed lookup | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Workflow job write/update | `repo_upsert_workflow_job`, `repo_update_workflow_job` | async template/worker job submit, adapter-readiness rejection, background running/completed/failed transitions, operator mark-failed | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Agent Plan / plan-evidence writes | `repo_upsert_agent_plan`, `repo_upsert_plan_evidence_manifest`, `repo_update_plan_evidence_manifest` | Agent Gateway plan create, plan-evidence manifest create, manifest verification persistence | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Agent Gateway enrollment/session admin reads | `repo_list_gateway_enrollments`, `repo_list_gateway_sessions` | `GET /api/agent-gateway/enrollments`, `GET /api/agent-gateway/sessions` | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Agent Gateway enrollment request writes | `repo_upsert_gateway_enrollment_request` | `POST /api/agent-gateway/enrollment/request` before approval and token issue | `python3 scripts/storage_boundary_sqlite_smoke.py`; `python3 scripts/enrollment_approval_workflow_smoke.py` |
| Agent Gateway task/run reads | `repo_pull_agent_gateway_tasks`, `repo_list_agent_gateway_tasks`, `repo_get_agent_gateway_task`, `repo_list_agent_gateway_runs`, `repo_get_agent_gateway_run` | `GET /api/agent-gateway/tasks/pull`, `GET /api/agent-gateway/tasks`, `GET /api/agent-gateway/tasks/:task_id`, `GET /api/agent-gateway/runs`, `GET /api/agent-gateway/runs/:run_id` | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Agent Gateway artifact/approval/memory reads | `repo_list_agent_gateway_artifacts`, `repo_list_agent_gateway_approvals`, `repo_list_agent_gateway_memories` | `GET /api/agent-gateway/artifacts`, `GET /api/agent-gateway/approvals`, `GET /api/agent-gateway/memories` | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Task/run write upsert | `repo_upsert_task`, `repo_upsert_run` | task create/import paths, Agent Gateway run start, mock/workflow run creation | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Evidence write upsert | `repo_upsert_approval`, `repo_upsert_evaluation`, `repo_upsert_artifact`, `repo_upsert_memory_candidate` | Agent Gateway approval/evaluation/artifact/memory writes, mock runtime artifact/evaluation/memory writes, adapter eval/memory imports | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Tool/runtime/audit write append | `repo_upsert_tool_call`, `repo_insert_runtime_event`, `repo_insert_audit_log` | Tool-call adapter imports, Agent Gateway tool call writes, runtime connector events, audit tamper-chain append | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Review decision updates | `repo_update_approval_decision`, `repo_update_memory_review_status`, `repo_update_tool_call_status` | Approval approve/reject, memory approve/reject, approval-driven tool status transitions | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Prepared-action exact-resume contract | `repo_upsert_prepared_action`, `repo_update_prepared_action_status`, `repo_claim_workspace_prepared_action`, `claim_prepared_action_execution`, `repo_list_workspace_prepared_actions`, `repo_get_workspace_prepared_action` | `prepared_action_approval_single_binding_v1` gives every non-null `approval_id` one global prepared-action binding; `prepared_action_cas_claim_v1` makes every external-side-effect resume win a database CAS `approved -> executing` transition and commit claim audit before its provider call; `prepared_action_stale_unknown_outcome_v1` moves stale `executing` rows to terminal `failed` with an unknown-outcome marker and forbids replay; `fixed_runtime_server_generated_identifiers_v1` makes fixed OpenClaw/Hermes `task_id`, `run_id`, `tool_call_id`, and `approval_id` server-generated; `legacy_prepared_action_lifecycle_migration_v1` preserves existing Free Local SQLite rows while widening the old lifecycle CHECK for `executing` and `failed` | `python3 scripts/storage_boundary_sqlite_smoke.py`; `python3 scripts/storage_postgres_write_helper_parity_smoke.py` |
| Notion export prepared-action integration | `notion_prepare_confirmed_export`, `notion_resume_prepared_export`, `post_notion_page` with configurable API base | `POST /api/integrations/notion/export-confirmed`, `POST /api/integrations/notion/export-report` when confirmed | `python3 scripts/notion_export_prepared_action_smoke.py` |
| Dify upload prepared-action integration | `dify_prepare_upload_text`, `dify_resume_upload_text`, `dify_upload_args` | `POST /api/integrations/dify/upload-text` when `confirm_upload` is true | `python3 scripts/dify_upload_prepared_action_smoke.py` |
| Hermes run-task prepared-action integration | `hermes_prepare_run_task`, `hermes_resume_run_task`, `hermes_run_task_args` | Workspace-admin authentication before id lookup; prepare rejects caller-supplied task/run/tool/approval ids, and resume uses the shared CAS claim for a single-winner `POST /api/integrations/hermes/run-task` exact resume when `confirm_run` is true | `python3 scripts/hermes_run_task_prepared_action_smoke.py` |
| Agnesfallback fixed-probe prepared-action integration | `agnesfallback_prepare_probe`, `agnesfallback_resume_probe`, `agnesfallback_probe_args` | `POST /api/integrations/hermes/cli-probe`, `POST /api/integrations/hermes/chat-completion-probe` when `confirm_run` is true | `python3 scripts/agnesfallback_probe_prepared_action_smoke.py` |
| Local brief prepared-action integration | `prepare_local_ai_brief`, `resume_local_ai_brief`, `local_ai_brief_args` | `POST /api/workflows/local-brief` when `confirm_run` is true | `python3 scripts/local_brief_prepared_action_smoke.py` |
| OpenClaw fixed-probe prepared-action integration | `openclaw_prepare_probe`, `openclaw_resume_probe`, `openclaw_probe_args` | Workspace-admin authentication before id lookup; prepare rejects caller-supplied task/run/tool/approval ids, and resume uses the shared CAS claim for a single-winner `POST /api/integrations/openclaw/probe` exact resume when `confirm_run` is true | `python3 scripts/openclaw_probe_prepared_action_smoke.py` |
| Customer-worker external-write prepared-action integration | `prepare_customer_worker_external_write`, `resume_customer_worker_external_write`, `customer_worker_external_write_args`, `repo_list_workspace_customer_worker_prepared_actions`, `customer_worker_prepared_actions_readback` | `POST /api/workflows/customer-worker-task`, `POST /api/workflows/customer-worker-task/submit` when `adapter` is Hermes/OpenClaw and `confirm_run` is true; `GET /api/workflows/customer-worker-prepared-actions` safe readback | `python3 scripts/customer_worker_prepared_action_smoke.py`; `python3 scripts/nextjs_customer_worker_prepared_action_smoke.py` |
| Postgres parity pre-container contract | generated Postgres-compatible DDL and placeholder translation contract from `server.SCHEMA_SQL` | future Postgres adapter using the same helper contract as SQLite | `python3 scripts/storage_postgres_contract_smoke.py` |
| Postgres container parity contract | generated schema plus representative task/run/tool/approval/prepared-action/plan-evidence fixture in a temporary Postgres container | BYOC Postgres migration readiness before a Python Postgres adapter is accepted | `python3 scripts/storage_postgres_container_smoke.py` |
| Postgres adapter SQL contract | SQLite helper qmark/named placeholder translation plus representative helper insert/update/select execution in a temporary Postgres container | optional psycopg adapter path without changing Free Local dependencies | `python3 scripts/storage_postgres_adapter_contract_smoke.py` |
| Optional psycopg adapter contract | `agentops_mis_storage.postgres` adapter executes generated schema plus representative helper SQL through psycopg in a temporary Postgres container | first reusable Python Postgres adapter primitive while keeping Free Local dependency-free | `python3 scripts/storage_postgres_optional_adapter_smoke.py` |
| Postgres boundary fixture parity | `agentops_mis_storage.parity_fixture` runs the same operations and queries through SQLite and the optional Postgres adapter, then compares normalized snapshots | storage adapter acceptance before route-level BYOC Postgres parity | `python3 scripts/storage_postgres_boundary_parity_smoke.py` |
| Postgres route read-model parity | Selected current API response shapes projected from the shared fixture compare identical on SQLite and Postgres | pre-HTTP route parity before a Postgres-backed server adapter can replace SQLite reads | `python3 scripts/storage_postgres_route_read_model_smoke.py` |
| Storage backend selection | `AGENTOPS_STORAGE_BACKEND` and `/api/storage/backend-status` expose the selected backend and fail closed for Postgres until all prerequisites are proven | prevents Enterprise/BYOC misconfiguration from silently using SQLite | `python3 scripts/storage_backend_selection_smoke.py` |
| Postgres HTTP read parity | `AGENTOPS_STORAGE_BACKEND=postgres` plus `AGENTOPS_POSTGRES_READ_ONLY_HTTP=1` starts the server on a temporary Postgres database, routes selected GET APIs through `PostgresAdapter`, and blocks POST/PATCH writes | first real server-backed Postgres route proof before widening read coverage or enabling writes | `python3 scripts/storage_postgres_http_read_parity_smoke.py` |
| Postgres CLI/API read parity | `AGENTOPS_BASE_URL` plus a temporary `AGENTOPS_CONFIG` drives selected `agentops` task/run/artifact/approval/memory/workflow-job and Agent Plan / plan-evidence list/get/verify commands against the Postgres read-only server while CLI write attempts fail closed | proves machine-facing Agent Gateway CLI/API reads are Postgres-backed without relying on browser APIs or local SQLite | `python3 scripts/storage_postgres_cli_read_parity_smoke.py` |
| Postgres write-helper parity | Selected `server.repo_*` task/run/tool/approval/prepared-action/evaluation/artifact/memory/workflow-job/Agent Plan/plan-evidence/audit/runtime-event write helpers run against temporary SQLite and Postgres with matching outcomes and snapshots while HTTP/CLI writes remain disabled | proves the helper layer can write BYOC Postgres before any routed write surface is allowed | `python3 scripts/storage_postgres_write_helper_parity_smoke.py` |
| Postgres routed task/execution/heartbeat-completion/evidence/plan/memory/approval/audit/write-plus-fixed-runtime-prepared-action write | `AGENTOPS_STORAGE_BACKEND=postgres`, `AGENTOPS_POSTGRES_READ_ONLY_HTTP=1`, and explicit `AGENTOPS_POSTGRES_WRITE_HTTP=1` allow only `POST /api/tasks`, scoped `POST /api/agent-gateway/tasks`, scoped `POST /api/agent-gateway/tasks/:task_id/claim`, scoped `POST /api/agent-gateway/runs/start`, scoped `POST /api/agent-gateway/heartbeat`, scoped `POST /api/agent-gateway/runs/:run_id/heartbeat`, scoped `POST /api/agent-gateway/tool-calls`, scoped `POST /api/agent-gateway/artifacts`, scoped `POST /api/agent-gateway/evaluations/submit`, scoped `POST /api/agent-gateway/agent-plans`, scoped `POST /api/agent-gateway/plan-evidence-manifests`, scoped `POST /api/agent-gateway/memories/propose`, scoped `POST /api/agent-gateway/approvals/request`, scoped `POST /api/agent-gateway/audit`, fixed `POST /api/integrations/openclaw/probe`, fixed `POST /api/integrations/hermes/run-task`, and row-gated `POST /api/approvals/:approval_id/approve` for those two fixed-runtime prepared actions to write through `PostgresAdapter`; absent tokens, missing scopes, body/header cross-workspace, cross-agent, same-workspace intruder, run heartbeat task mismatch, terminal run revival, completion task/agent sync, manifest binding mismatch, memory run/task mismatch, approval task/tool/requester mismatch, approved approval overwrite, non-prepared approval decisions, audit entity/run/task mismatch, knowledge index, non-fixed live-runtime routes, and broad admin mutations remain blocked | first real human/API plus Agent Gateway task-create, claim, run-start, agent heartbeat, run progress heartbeat, run completion heartbeat, tool/evaluation/artifact evidence-write, Agent Plan, verified plan-evidence manifest, memory candidate, approval request, run/task-bound audit proof, and fixed Hermes/OpenClaw prepare -> approve -> cross-workspace hidden -> two-process Postgres resume race -> one provider-call/claim-audit winner -> consumed/replay-blocked proof without opening knowledge, arbitrary runtime, or broad admin mutations | `python3 scripts/storage_postgres_http_write_task_smoke.py` |
| Postgres Agent Gateway identity lifecycle | Explicit Postgres write mode allowlists registration, enrollment policy preview/request/create/approved issue/rotate/revoke, session create/revoke, and only the enrollment-bound human approval decision; production uses distinct workspace-specific admin key-map credentials, request ids plus approval bindings/decisions are immutable, approval/request rows use one lock order, token/session revocation locks every transitioned row, and `repo_upsert_gateway_enrollment_request` keeps the request write on the shared adapter boundary | proves the durable Agent Gateway can establish, rotate, and revoke scoped worker identity on BYOC Postgres with global-only production admin, malformed key map, anonymous calls, and cross-workspace ids fail-closed/hidden; two independent MIS processes prove approve/issue deadlock freedom, repeated approval idempotence, issue/rotation single-winner behavior, and concurrent token/session-revoke single-winner audit evidence; repeated revoke adds no audit evidence, and token/session omission, non-nesting, and parent revoke cascade remain intact | `python3 scripts/storage_postgres_gateway_lifecycle_smoke.py` |
| TypeScript-owned Postgres Agent Gateway task/run/plan/evidence core | Exact Next.js task, Agent Plan, run-start, run-heartbeat, tool-call, evaluation-submit, artifact, and plan-evidence-manifest routes default to direct Postgres ownership in production and keep explicit local proxy rollback; they validate token/session parent state, route scope, workspace and agent binding before scoped ledger/runtime/audit transactions, use task-before-run-before-plan/manifest and parent-token-before-session lock orders, serialize each immutable ID, and share Postgres advisory audit lock `1095779668` with Python | proves the commercial control plane can create/list tasks, submit immutable verified plans, require a plan before non-mock execution, persist progress/completion and redacted evidence, and verify immutable closure manifests without a Python API process; hides other-workspace rows; reserves approval status for humans; blocks missing-plan, approval-pending, missing-evidence, rebind, terminal-revival, evidence-rewrite and risk-downgrade attempts; gives concurrent state/evidence writes one winner; races session auth against parent revocation without lock inversion; and recomputes row after-hashes plus one cross-language tamper chain | `python3 scripts/nextjs_postgres_control_plane_tasks_smoke.py` |
| TypeScript-owned customer-delivery approval request | Exact Next.js `POST /api/mis/agent-gateway/approvals/request` defaults to direct Postgres ownership in production and permits Python only in explicit Free Local proxy mode; `approvals:request`, token/session, workspace, agent, completed run, current verified Hermes/OpenClaw evidence, bounded reason, server expiry, Human-owned approver attribution, task-before-run lock order, immutable replay, and ledger omission rules are enforced before creating a pending row | proves a real Worker can move a completed task to `waiting_approval` without changing its completed run, produce one runtime/audit receipt, hide cross-workspace IDs, and avoid duplicate evidence under replay/concurrency; schema v5 rejects historical duplicates without deletion and adds a partial unique index for one customer-delivery approval per globally unique run | `npm --prefix ui/next-app run test:customer-delivery-approval-request-contract`; `python3 scripts/nextjs_postgres_real_worker_human_review_smoke.py --postgres-dsn <isolated-postgres-dsn>` |
| Postgres CLI/API write parity | `AGENTOPS_BASE_URL`, a temporary `AGENTOPS_CONFIG`, and seeded scoped Gateway tokens drive actual `agentops` CLI writes against the Postgres write server while read-only, missing-scope, and non-allowlisted CLI writes fail closed | proves machine-facing Agent Gateway CLI commands can create, claim, start, heartbeat, write evidence, submit Agent Plan / plan-evidence, propose memory, request approval, emit audit, and complete a run through the Postgres adapter without relying on direct HTTP fixtures | `python3 scripts/storage_postgres_cli_write_parity_smoke.py` |
| Postgres BYOC backup/restore | `agentops_postgres_backup.py` creates a custom-format archive plus mandatory `postgres_backup_manifest_v1`, verifies hash/TOC, and restores only after explicit target-state confirmation; the container smoke compares source/restored fixture counts and proves overwrite pre-backup/tamper rejection | `postgres_backup_restore_v1` closes the customer-owned Postgres recovery path; file presence is availability only and handoff requires a non-skipped receipt | `python3 scripts/agentops_postgres_backup_smoke.py` |

The helpers deliberately keep the existing SQLite row shape and ordering. They
only centralize workspace filters and detail assembly so a future adapter can
match behavior before Postgres is introduced.

## Next Boundary Candidates

| Candidate | Why next | Required proof before Postgres |
| --- | --- | --- |
| Prepared-action route integration audit | Notion export, Dify upload, Hermes default run-task, Agnesfallback fixed probes, local brief, OpenClaw fixed probe, and customer-worker external writes are covered; future external side-effect routes must be added here before Postgres parity claims | Connector/runtime smokes that prove no provider call before approval and exact one-shot resume after approval |
| Postgres adapter contract | SQLite helpers now cover core ledger/evidence writes, schema/container parity passes, representative helper SQL translation is locked, and optional psycopg execution is proven | Python Postgres adapter smoke with identical storage-boundary fixtures and response-shape comparison |

## Postgres Parity Rule

Postgres work may start only after the SQLite helper for a flow has:

- one isolated `AGENTOPS_DB_PATH` smoke that exercises create, read, filter, and
  cross-workspace exclusion;
- no raw secrets, prompts, responses, local DB files, generated exports, or
  private transcripts in the diff;
- unchanged HTTP/CLI response shape for the current Python/SQLite path.

The pre-container Postgres contract must also pass:

- `python3 scripts/storage_postgres_contract_smoke.py`

The container parity contract must pass before Postgres adapter work can claim
real BYOC evidence:

- `python3 scripts/storage_postgres_container_smoke.py`

The adapter SQL contract must pass before adding a Python Postgres execution
adapter:

- `python3 scripts/storage_postgres_adapter_contract_smoke.py`

The optional psycopg adapter primitive must pass before routing server helpers
through Postgres:

- `python3 scripts/storage_postgres_optional_adapter_smoke.py`

The shared boundary fixture parity smoke must pass before claiming a helper set
has identical SQLite and Postgres outcomes:

- `python3 scripts/storage_postgres_boundary_parity_smoke.py`

The route read-model parity smoke must pass before claiming selected current
HTTP response shapes are Postgres-ready:

- `python3 scripts/storage_postgres_route_read_model_smoke.py`

The backend selection smoke must pass before exposing Postgres as a deployable
server storage backend:

- `python3 scripts/storage_backend_selection_smoke.py`

The Postgres HTTP read parity smoke must pass before claiming any server route
is actually Postgres-backed:

- `python3 scripts/storage_postgres_http_read_parity_smoke.py`

The Postgres CLI read parity smoke must pass before claiming agent-facing
CLI/API reads are actually Postgres-backed:

- `python3 scripts/storage_postgres_cli_read_parity_smoke.py`

The Postgres write-helper parity smoke must pass before enabling any
Postgres-backed write route. Routed write support starts with an explicit
human/API plus Agent Gateway task-create allowlist; broader HTTP/CLI writes
need their own smoke first:

- `python3 scripts/storage_postgres_write_helper_parity_smoke.py`
- `python3 scripts/storage_postgres_http_write_task_smoke.py`
- `python3 scripts/storage_postgres_gateway_lifecycle_smoke.py`
- `python3 scripts/storage_postgres_cli_write_parity_smoke.py`
