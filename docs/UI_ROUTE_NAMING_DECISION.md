# UI Route Naming Decision

Contract: `ui_route_naming_decision_v1`

Gate: `gate_4_ui_api_parity_before_nextjs`

Machine-readable contract: `docs/UI_ROUTE_NAMING_DECISION.json`

## Decision

Task and run operator routes now use `/workspace` as the commercial namespace
in both the Vite primary UI and the Next.js parity track. Existing Vite
`/admin` task/run routes are retired to redirect-only compatibility deep links,
and Next `/admin` task/run routes remain redirect aliases.

The navigation inventory is verified by `ui_navigation_inventory_v1`: Next and
Vite primary task/run navigation use `/workspace`, while `/admin` task/run
routes are aliases only. The task/run retirement packet is now executed by
`ui_route_retirement_packet_v1`.

## Route Pairs

| Matrix entry | Legacy Vite route | Next alias | Target Next route | Retirement |
|---|---|---|---|---|
| `task_detail` | `/admin/tasks/:id` | `/admin/tasks/:taskId` | `/workspace/tasks/:taskId` | Executed |
| `run_ledger` | `/admin/runs` | `/admin/runs` | `/workspace/runs` | Executed |
| `run_detail` | `/admin/runs/:id` | `/admin/runs/:runId` | `/workspace/runs/:runId` | Executed |

## Verification

```bash
python3 scripts/ui_route_naming_decision_smoke.py
python3 scripts/ui_legacy_route_alias_smoke.py
python3 scripts/ui_navigation_inventory_smoke.py
python3 scripts/ui_route_retirement_packet_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/ui_task_run_route_parity_smoke.py
python3 scripts/vite_playwright_snapshot_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
```
