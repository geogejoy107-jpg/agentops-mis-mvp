# UI Route Retirement Packet

Contract: `ui_route_retirement_packet_v1`

Gate: `gate_4_ui_api_parity_before_nextjs`

Machine-readable contract: `docs/UI_ROUTE_RETIREMENT_PACKET.json`

## Decision

This packet executes the task/run legacy `/admin` route retirement for the
commercial migration branch. The old Vite task/run content routes are now
redirect-only deep links, while `/workspace` is the canonical task/run
namespace in both Vite primary navigation and the Next.js App Router track.

The current state is:

- Next primary task/run navigation uses `/workspace`.
- Next `/admin/tasks/:taskId`, `/admin/runs`, and `/admin/runs/:runId` remain
  compatibility redirect aliases.
- Vite `/admin/tasks/:id`, `/admin/runs`, and `/admin/runs/:id` are retired to
  workspace redirect aliases.
- Vite primary/internal task and run links now use `/workspace/tasks/:id`,
  `/workspace/runs`, and `/workspace/runs/:id`.
- `retirement_allowed` is `true` for `task_detail`, `run_ledger`, and
  `run_detail` only; every other Vite route still needs its own explicit
  route-pair commit.

## Candidate Routes

| Matrix entry | Legacy Vite route | Next alias | Canonical Next route | Current state |
|---|---|---|---|---|
| `task_detail` | `/admin/tasks/:id` | `/admin/tasks/:taskId` | `/workspace/tasks/:taskId` | Retired to workspace redirect |
| `run_ledger` | `/admin/runs` | `/admin/runs` | `/workspace/runs` | Retired to workspace redirect |
| `run_detail` | `/admin/runs/:id` | `/admin/runs/:runId` | `/workspace/runs/:runId` | Retired to workspace redirect |

## Retirement Commit Requirements

Every future retirement commit for any other route must name the exact route
pair being retired, preserve a deep-link redirect or alias, update the UI/API
parity matrix, and rerun Vite plus Next browser evidence after the route
change.

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
