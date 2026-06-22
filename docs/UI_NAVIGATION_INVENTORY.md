# UI Navigation Inventory

Contract: `ui_navigation_inventory_v1`

Gate: `gate_4_ui_api_parity_before_nextjs`

Machine-readable contract: `docs/UI_NAVIGATION_INVENTORY.json`

## Decision

Task and run navigation in the Next.js commercial parity track uses
`/workspace` as the primary namespace. The Next `/admin/tasks/:taskId`,
`/admin/runs`, and `/admin/runs/:runId` routes are compatibility redirect
aliases only; they are not primary navigation targets.

This inventory still does not retire the Vite routes. It proves the Next
navigation surface has moved to `/workspace`, leaving only an explicit route
retirement commit before any legacy task/run route can be removed.

## Canonical Next Routes

| Surface | Canonical route |
|---|---|
| Task list | `/workspace/tasks` |
| Task detail | `/workspace/tasks/:taskId` |
| Run ledger | `/workspace/runs` |
| Run detail | `/workspace/runs/:runId` |

## Allowed Compatibility Aliases

| Alias | Target |
|---|---|
| `/admin/tasks/:taskId` | `/workspace/tasks/:taskId` |
| `/admin/runs` | `/workspace/runs` |
| `/admin/runs/:runId` | `/workspace/runs/:runId` |

## Verification

```bash
python3 scripts/ui_navigation_inventory_smoke.py
python3 scripts/ui_route_naming_decision_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/nextjs_parity_smoke.py
```
