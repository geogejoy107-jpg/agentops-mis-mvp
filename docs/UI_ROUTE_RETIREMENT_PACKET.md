# UI Route Retirement Packet

Contract: `ui_route_retirement_packet_v1`

Gate: `gate_4_ui_api_parity_before_nextjs`

Machine-readable contract: `docs/UI_ROUTE_RETIREMENT_PACKET.json`

## Decision

This packet executes the task/run plus covered admin operations legacy `/admin`
route retirement for the commercial migration branch. The old Vite content
routes are now redirect-only deep links, while `/workspace` is the canonical
namespace in both Vite primary navigation and the Next.js App Router track.

The current state is:

- Next primary navigation for the covered surfaces uses `/workspace`.
- Next `/admin/tasks/:taskId`, `/admin/runs`, and `/admin/runs/:runId` remain
  compatibility redirect aliases.
- Vite retired `/admin` task/run and admin-operations routes are retired to
  workspace redirect aliases.
- Vite primary/internal task, run, agent-detail, evaluation, tool-call,
  connector, Notion base, template, and audit links now use `/workspace`.
- `retirement_allowed` is `true` for the route pairs named below. Control Tower
  `/admin` and Worker Console same-path ownership remain candidate-only.

## Candidate Routes

| Matrix entry | Legacy Vite route | Next alias | Canonical Next route | Current state |
|---|---|---|---|---|
| `task_detail` | `/admin/tasks/:id` | `/admin/tasks/:taskId` | `/workspace/tasks/:taskId` | Retired to workspace redirect |
| `run_ledger` | `/admin/runs` | `/admin/runs` | `/workspace/runs` | Retired to workspace redirect |
| `run_detail` | `/admin/runs/:id` | `/admin/runs/:runId` | `/workspace/runs/:runId` | Retired to workspace redirect |
| `agent_detail` | `/admin/agents/:id` | Not required | `/workspace/agents/:agentId` | Retired to workspace redirect |
| `evaluation_room` | `/admin/evaluations` | Not required | `/workspace/evaluations` | Retired to workspace redirect |
| `tool_calls` | `/admin/toolcalls` | Not required | `/workspace/tool-calls` | Retired to workspace redirect |
| `runtime_connectors` | `/admin/connectors` | Not required | `/workspace/connectors` | Retired to workspace redirect |
| `external_bases_notion` | `/admin/bases/notion` | Not required | `/workspace/external-bases/notion` | Retired to workspace redirect |
| `template_switching` | `/admin/templates` | Not required | `/workspace/templates` | Retired to workspace redirect |
| `audit` | `/admin/audit` | Not required | `/workspace/audit` | Retired to workspace redirect |

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
python3 scripts/ui_admin_operations_route_retirement_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
```
