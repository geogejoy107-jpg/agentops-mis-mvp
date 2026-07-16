# UI Route Naming Decision

Contract: `ui_route_naming_decision_v1`

Gate: `gate_4_ui_api_parity_before_nextjs`

Machine-readable contract: `docs/UI_ROUTE_NAMING_DECISION.json`

## Decision

Task, run, and covered admin operations routes now use `/workspace` as the
commercial namespace in both the Vite primary UI and the Next.js parity track.
Existing Vite `/admin` routes for these surfaces are retired to redirect-only
compatibility deep links, and Next `/admin` task/run routes remain redirect
aliases.

The navigation inventory is verified by `ui_navigation_inventory_v1`: Next and
Vite primary navigation use `/workspace`, while retired `/admin` routes are
aliases only. The task/run and admin-operations retirement packet is now
executed by `ui_route_retirement_packet_v1` and
`ui_admin_operations_route_retirement_v1`.

## Route Pairs

| Matrix entry | Legacy Vite route | Next alias | Target Next route | Retirement |
|---|---|---|---|---|
| `task_detail` | `/admin/tasks/:id` | `/admin/tasks/:taskId` | `/workspace/tasks/:taskId` | Executed |
| `run_ledger` | `/admin/runs` | `/admin/runs` | `/workspace/runs` | Executed |
| `run_detail` | `/admin/runs/:id` | `/admin/runs/:runId` | `/workspace/runs/:runId` | Executed |
| `agent_detail` | `/admin/agents/:id` | `not_required_for_vite_only_legacy_alias` | `/workspace/agents/:agentId` | Executed |
| `evaluation_room` | `/admin/evaluations` | `not_required_for_vite_only_legacy_alias` | `/workspace/evaluations` | Executed |
| `tool_calls` | `/admin/toolcalls` | `not_required_for_vite_only_legacy_alias` | `/workspace/tool-calls` | Executed |
| `runtime_connectors` | `/admin/connectors` | `not_required_for_vite_only_legacy_alias` | `/workspace/connectors` | Executed |
| `external_bases_notion` | `/admin/bases/notion` | `not_required_for_vite_only_legacy_alias` | `/workspace/external-bases/notion` | Executed |
| `template_switching` | `/admin/templates` | `not_required_for_vite_only_legacy_alias` | `/workspace/templates` | Executed |
| `audit` | `/admin/audit` | `not_required_for_vite_only_legacy_alias` | `/workspace/audit` | Executed |

## Verification

```bash
python3 scripts/ui_route_naming_decision_smoke.py
python3 scripts/ui_legacy_route_alias_smoke.py
python3 scripts/ui_navigation_inventory_smoke.py
python3 scripts/ui_route_retirement_packet_smoke.py
python3 scripts/ui_admin_operations_route_retirement_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/ui_task_run_route_parity_smoke.py
python3 scripts/vite_playwright_snapshot_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
```
