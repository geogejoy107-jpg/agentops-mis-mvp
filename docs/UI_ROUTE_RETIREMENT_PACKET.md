# UI Route Retirement Packet

Contract: `ui_route_retirement_packet_v1`

Gate: `gate_4_ui_api_parity_before_nextjs`

Machine-readable contract: `docs/UI_ROUTE_RETIREMENT_PACKET.json`

## Decision

This packet prepares the task/run legacy `/admin` routes for a later explicit
retirement commit. It does not retire any Vite route by itself.

The current state is:

- Next primary task/run navigation uses `/workspace`.
- Next `/admin/tasks/:taskId`, `/admin/runs`, and `/admin/runs/:runId` remain
  compatibility redirect aliases.
- Vite `/admin/tasks/:id`, `/admin/runs`, and `/admin/runs/:id` remain live
  legacy compatibility routes.
- `retirement_allowed` remains `false` until a route-pair-specific retirement
  commit updates the matrix and reruns browser evidence.

## Candidate Routes

| Matrix entry | Legacy Vite route | Next alias | Canonical Next route | Current state |
|---|---|---|---|---|
| `task_detail` | `/admin/tasks/:id` | `/admin/tasks/:taskId` | `/workspace/tasks/:taskId` | Candidate only |
| `run_ledger` | `/admin/runs` | `/admin/runs` | `/workspace/runs` | Candidate only |
| `run_detail` | `/admin/runs/:id` | `/admin/runs/:runId` | `/workspace/runs/:runId` | Candidate only |

## Retirement Commit Requirements

Every future retirement commit must name the exact route pair being retired,
preserve a deep-link redirect or alias, update the UI/API parity matrix, and
rerun Vite plus Next browser evidence after the route change.

The commit must not change Agent Gateway CLI/API/MCP contracts and must not
commit local databases, generated artifacts, raw prompts, raw responses, private
transcripts, or secrets.

## Verification

```bash
python3 scripts/ui_route_retirement_packet_smoke.py
python3 scripts/ui_route_naming_decision_smoke.py
python3 scripts/ui_navigation_inventory_smoke.py
python3 scripts/ui_legacy_route_alias_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
```
