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

The helpers deliberately keep the existing SQLite row shape and ordering. They
only centralize workspace filters and detail assembly so a future adapter can
match behavior before Postgres is introduced.

## Next Boundary Candidates

| Candidate | Why next | Required proof before Postgres |
| --- | --- | --- |
| Approval/evaluation/artifact list helpers | They join tasks/runs for workspace isolation and are user-visible ledgers | Helper smoke plus existing workspace RBAC smoke |
| Audit query helper | Audit evidence is part of Team/Enterprise compliance surface | Helper smoke proving task/run/job metadata scoping |
| Agent Gateway read helpers | CLI/API/MCP are the durable agent contract | Scope matrix and workspace isolation smokes |
| Workflow job repository | BYOC deployments need stuck-job recovery and retention | Job recovery smoke against isolated SQLite |

## Postgres Parity Rule

Postgres work may start only after the SQLite helper for a flow has:

- one isolated `AGENTOPS_DB_PATH` smoke that exercises create, read, filter, and
  cross-workspace exclusion;
- no raw secrets, prompts, responses, local DB files, generated exports, or
  private transcripts in the diff;
- unchanged HTTP/CLI response shape for the current Python/SQLite path.
