# UI Route Naming Decision

Contract: `ui_route_naming_decision_v1`

Gate: `gate_4_ui_api_parity_before_nextjs`

Machine-readable contract: `docs/UI_ROUTE_NAMING_DECISION.json`

## Decision

Task and run operator routes use `/workspace` as the future commercial
namespace in the Next.js parity track. Existing Vite `/admin` task/run routes
remain legacy compatibility routes until explicit retirement gates pass.

This decision does not retire Vite routes and does not create redirects by
itself. The current Next.js parity track now provides backward-compatible
redirect aliases for the task/run legacy deep links. The navigation inventory is
now verified by `ui_navigation_inventory_v1`: Next primary task/run navigation
uses `/workspace`, and Next `/admin` task/run routes are redirect aliases only.
Retirement remains blocked until an explicit route retirement commit on the
exact route pair being retired.

## Route Pairs

| Matrix entry | Legacy Vite route | Next alias | Target Next route | Retirement |
|---|---|---|---|---|
| `task_detail` | `/admin/tasks/:id` | `/admin/tasks/:taskId` | `/workspace/tasks/:taskId` | Not allowed |
| `run_ledger` | `/admin/runs` | `/admin/runs` | `/workspace/runs` | Not allowed |
| `run_detail` | `/admin/runs/:id` | `/admin/runs/:runId` | `/workspace/runs/:runId` | Not allowed |

## Verification

```bash
python3 scripts/ui_route_naming_decision_smoke.py
python3 scripts/ui_legacy_route_alias_smoke.py
python3 scripts/ui_navigation_inventory_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/ui_task_run_route_parity_smoke.py
python3 scripts/vite_playwright_snapshot_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
```
