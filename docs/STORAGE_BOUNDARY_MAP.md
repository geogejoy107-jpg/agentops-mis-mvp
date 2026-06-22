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
| Agent Gateway task/run reads | `repo_pull_agent_gateway_tasks`, `repo_list_agent_gateway_tasks`, `repo_get_agent_gateway_task`, `repo_list_agent_gateway_runs`, `repo_get_agent_gateway_run` | `GET /api/agent-gateway/tasks/pull`, `GET /api/agent-gateway/tasks`, `GET /api/agent-gateway/tasks/:task_id`, `GET /api/agent-gateway/runs`, `GET /api/agent-gateway/runs/:run_id` | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Agent Gateway artifact/approval/memory reads | `repo_list_agent_gateway_artifacts`, `repo_list_agent_gateway_approvals`, `repo_list_agent_gateway_memories` | `GET /api/agent-gateway/artifacts`, `GET /api/agent-gateway/approvals`, `GET /api/agent-gateway/memories` | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Task/run write upsert | `repo_upsert_task`, `repo_upsert_run` | task create/import paths, Agent Gateway run start, mock/workflow run creation | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Evidence write upsert | `repo_upsert_approval`, `repo_upsert_evaluation`, `repo_upsert_artifact`, `repo_upsert_memory_candidate` | Agent Gateway approval/evaluation/artifact/memory writes, mock runtime artifact/evaluation/memory writes, adapter eval/memory imports | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Tool/runtime/audit write append | `repo_upsert_tool_call`, `repo_insert_runtime_event`, `repo_insert_audit_log` | Tool-call adapter imports, Agent Gateway tool call writes, runtime connector events, audit tamper-chain append | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Review decision updates | `repo_update_approval_decision`, `repo_update_memory_review_status`, `repo_update_tool_call_status` | Approval approve/reject, memory approve/reject, approval-driven tool status transitions | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Prepared-action exact-resume contract | `repo_upsert_prepared_action`, `repo_update_prepared_action_status`, `repo_list_workspace_prepared_actions`, `repo_get_workspace_prepared_action` | External side-effect preparation ledger, approval binding, exact-resume argument hash/snapshot, consumed result evidence | `python3 scripts/storage_boundary_sqlite_smoke.py` |
| Notion export prepared-action integration | `notion_prepare_confirmed_export`, `notion_resume_prepared_export`, `post_notion_page` with configurable API base | `POST /api/integrations/notion/export-confirmed`, `POST /api/integrations/notion/export-report` when confirmed | `python3 scripts/notion_export_prepared_action_smoke.py` |
| Dify upload prepared-action integration | `dify_prepare_upload_text`, `dify_resume_upload_text`, `dify_upload_args` | `POST /api/integrations/dify/upload-text` when `confirm_upload` is true | `python3 scripts/dify_upload_prepared_action_smoke.py` |
| Hermes run-task prepared-action integration | `hermes_prepare_run_task`, `hermes_resume_run_task`, `hermes_run_task_args` | `POST /api/integrations/hermes/run-task` when `confirm_run` is true | `python3 scripts/hermes_run_task_prepared_action_smoke.py` |
| Agnesfallback fixed-probe prepared-action integration | `agnesfallback_prepare_probe`, `agnesfallback_resume_probe`, `agnesfallback_probe_args` | `POST /api/integrations/hermes/cli-probe`, `POST /api/integrations/hermes/chat-completion-probe` when `confirm_run` is true | `python3 scripts/agnesfallback_probe_prepared_action_smoke.py` |
| OpenClaw fixed-probe prepared-action integration | `openclaw_prepare_probe`, `openclaw_resume_probe`, `openclaw_probe_args` | `POST /api/integrations/openclaw/probe` when `confirm_run` is true | `python3 scripts/openclaw_probe_prepared_action_smoke.py` |
| Customer-worker external-write prepared-action integration | `prepare_customer_worker_external_write`, `resume_customer_worker_external_write`, `customer_worker_external_write_args` | `POST /api/workflows/customer-worker-task`, `POST /api/workflows/customer-worker-task/submit` when `adapter` is Hermes/OpenClaw and `confirm_run` is true | `python3 scripts/customer_worker_prepared_action_smoke.py` |
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
| Postgres routed task/execution-start write | `AGENTOPS_STORAGE_BACKEND=postgres`, `AGENTOPS_POSTGRES_READ_ONLY_HTTP=1`, and explicit `AGENTOPS_POSTGRES_WRITE_HTTP=1` allow only `POST /api/tasks`, scoped `POST /api/agent-gateway/tasks`, scoped `POST /api/agent-gateway/tasks/:task_id/claim`, and scoped `POST /api/agent-gateway/runs/start` to write through `PostgresAdapter`; absent tokens, missing scopes, body/header cross-workspace, cross-agent, same-workspace intruder, and broader evidence writes remain blocked | first real human/API plus Agent Gateway task-create, claim, and run-start proof through the Postgres adapter without opening tool/eval/artifact/live-runtime writes or broad admin mutations | `python3 scripts/storage_postgres_http_write_task_smoke.py` |

The helpers deliberately keep the existing SQLite row shape and ordering. They
only centralize workspace filters and detail assembly so a future adapter can
match behavior before Postgres is introduced.

## Next Boundary Candidates

| Candidate | Why next | Required proof before Postgres |
| --- | --- | --- |
| Prepared-action route integration audit | Notion export, Dify upload, Hermes default run-task, Agnesfallback fixed probes, OpenClaw fixed probe, and customer-worker external writes are covered; future external side-effect routes must be added here before Postgres parity claims | Connector/runtime smokes that prove no provider call before approval and exact one-shot resume after approval |
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
