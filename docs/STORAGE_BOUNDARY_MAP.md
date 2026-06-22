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

The helpers deliberately keep the existing SQLite row shape and ordering. They
only centralize workspace filters and detail assembly so a future adapter can
match behavior before Postgres is introduced.

## Next Boundary Candidates

| Candidate | Why next | Required proof before Postgres |
| --- | --- | --- |
| Prepared-action contract/schema | The current commercial branch has no prepared-actions table or exact-resume side-effect contract yet | Dedicated schema/contract smoke before any external side-effect migration claim |
| Postgres adapter contract | SQLite helpers now cover core ledger and evidence writes; next step is a second adapter exercising the same helper contract | SQLite smoke parity plus Postgres container smoke with identical fixtures |

## Postgres Parity Rule

Postgres work may start only after the SQLite helper for a flow has:

- one isolated `AGENTOPS_DB_PATH` smoke that exercises create, read, filter, and
  cross-workspace exclusion;
- no raw secrets, prompts, responses, local DB files, generated exports, or
  private transcripts in the diff;
- unchanged HTTP/CLI response shape for the current Python/SQLite path.
