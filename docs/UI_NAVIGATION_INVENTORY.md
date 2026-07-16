# UI Navigation Inventory

Contract: `ui_navigation_inventory_v1`

Gate: `gate_4_ui_api_parity_before_nextjs`

Machine-readable contract: `docs/UI_NAVIGATION_INVENTORY.json`

## Decision

Task, run, and covered admin operations navigation in both the Next.js
commercial parity track and the Vite primary UI uses `/workspace` as the primary
namespace. The Next `/admin/tasks/:taskId`, `/admin/runs`, and
`/admin/runs/:runId` routes are compatibility redirect aliases only; the Vite
retired `/admin` task/run and admin-operations routes are also redirect aliases
only.

This inventory records the explicit route retirement executed by
`ui_route_retirement_packet_v1` and
`ui_admin_operations_route_retirement_v1`. Control Tower `/admin` and Worker
Console same-path ownership remain blocked until their own route-pair retirement
evidence is committed.

## Canonical Next Routes

| Surface | Canonical route |
|---|---|
| Task list | `/workspace/tasks` |
| Task detail | `/workspace/tasks/:taskId` |
| Run ledger | `/workspace/runs` |
| Run detail | `/workspace/runs/:runId` |
| Agent detail | `/workspace/agents/:agentId` |
| Evaluation room | `/workspace/evaluations` |
| Tool calls | `/workspace/tool-calls` |
| Runtime connectors | `/workspace/connectors` |
| Notion external base | `/workspace/external-bases/notion` |
| Templates | `/workspace/templates` |
| Audit | `/workspace/audit` |

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
| Agent detail | `/workspace/agents/:id` |
| Evaluation room | `/workspace/evaluations` |
| Tool calls | `/workspace/tool-calls` |
| Runtime connectors | `/workspace/connectors` |
| Notion external base | `/workspace/external-bases/notion` |
| Templates | `/workspace/templates` |
| Audit | `/workspace/audit` |

## Vite Compatibility Aliases

| Alias | Target |
|---|---|
| `/admin/tasks/:id` | `/workspace/tasks/:id` |
| `/admin/runs` | `/workspace/runs` |
| `/admin/runs/:id` | `/workspace/runs/:id` |
| `/admin/agents/:id` | `/workspace/agents/:id` |
| `/admin/evaluations` | `/workspace/evaluations` |
| `/admin/toolcalls` | `/workspace/tool-calls` |
| `/admin/connectors` | `/workspace/connectors` |
| `/admin/bases/notion` | `/workspace/external-bases/notion` |
| `/admin/templates` | `/workspace/templates` |
| `/admin/audit` | `/workspace/audit` |

## Verification

```bash
python3 scripts/ui_navigation_inventory_smoke.py
python3 scripts/ui_route_retirement_packet_smoke.py
python3 scripts/ui_admin_operations_route_retirement_smoke.py
python3 scripts/ui_route_naming_decision_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/nextjs_parity_smoke.py
```
