# UI Navigation Inventory

Contract: `ui_navigation_inventory_v1`

Gate: `gate_4_ui_api_parity_before_nextjs`

Machine-readable contract: `docs/UI_NAVIGATION_INVENTORY.json`

## Decision

Task and run navigation in both the Next.js commercial parity track and the
Vite primary UI uses `/workspace` as the primary namespace. The Next
`/admin/tasks/:taskId`, `/admin/runs`, and `/admin/runs/:runId` routes are
compatibility redirect aliases only; the Vite `/admin/tasks/:id`,
`/admin/runs`, and `/admin/runs/:id` routes are also redirect aliases only.

This inventory records the explicit task/run route retirement executed by
`ui_route_retirement_packet_v1`. Other legacy routes remain blocked until their
own route-pair retirement evidence is committed.

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

## Canonical Vite Routes

| Surface | Canonical route |
|---|---|
| Task list | `/workspace/tasks` |
| Task detail | `/workspace/tasks/:id` |
| Run ledger | `/workspace/runs` |
| Run detail | `/workspace/runs/:id` |

## Verification

```bash
python3 scripts/ui_navigation_inventory_smoke.py
python3 scripts/ui_route_retirement_packet_smoke.py
python3 scripts/ui_route_naming_decision_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/nextjs_parity_smoke.py
```
