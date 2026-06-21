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

The helpers deliberately keep the existing SQLite row shape and ordering. They
only centralize workspace filters and detail assembly so a future adapter can
match behavior before Postgres is introduced.

## Next Boundary Candidates

| Candidate | Why next | Required proof before Postgres |
| --- | --- | --- |
| Agent Gateway read helpers | CLI/API/MCP are the durable agent contract | Scope matrix and workspace isolation smokes |
| Write-path repositories | Postgres parity needs create/update behavior centralized after read helpers are locked | Existing workflow smokes plus isolated write helper smoke |

## Postgres Parity Rule

Postgres work may start only after the SQLite helper for a flow has:

- one isolated `AGENTOPS_DB_PATH` smoke that exercises create, read, filter, and
  cross-workspace exclusion;
- no raw secrets, prompts, responses, local DB files, generated exports, or
  private transcripts in the diff;
- unchanged HTTP/CLI response shape for the current Python/SQLite path.
