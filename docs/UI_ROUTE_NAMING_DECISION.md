# UI Route Naming Decision

Contract: `ui_route_naming_decision_v1`

Gate: `gate_4_ui_api_parity_before_nextjs`

Machine-readable contract: `docs/UI_ROUTE_NAMING_DECISION.json`

## Decision

Task and run operator routes use `/workspace` as the future commercial
namespace in the Next.js parity track. Existing Vite `/admin` task/run routes
remain legacy compatibility routes until explicit retirement gates pass.

This decision does not retire Vite routes and does not create redirects by
itself. Retirement remains blocked until a later cutover proves backward
compatible redirects or aliases, navigation inventory updates, browser
snapshots, and read-model parity on the exact route pair being retired.

## Route Pairs

| Matrix entry | Legacy Vite route | Target Next route | Retirement |
|---|---|---|---|
| `task_detail` | `/admin/tasks/:id` | `/workspace/tasks/:taskId` | Not allowed |
| `run_ledger` | `/admin/runs` | `/workspace/runs` | Not allowed |
| `run_detail` | `/admin/runs/:id` | `/workspace/runs/:runId` | Not allowed |

## Verification

```bash
python3 scripts/ui_route_naming_decision_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/ui_task_run_route_parity_smoke.py
python3 scripts/vite_playwright_snapshot_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
```
