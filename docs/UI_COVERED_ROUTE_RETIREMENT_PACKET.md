# UI Covered Route Retirement Packet

Contract: `ui_covered_route_retirement_packet_v1`

Gate: `gate_4_ui_api_parity_before_nextjs`

Machine-readable contract: `docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json`

## Decision

This packet prepares the newly covered Control Tower and Worker Console route
pairs for a later explicit retirement commit. It does not retire any Vite route
by itself.

The current state is:

- `control_tower` is covered by split Next routes: `/workspace`,
  `/workspace/agents`, `/workspace/governance`, and `/workspace/deployment`.
- Vite `/admin` remains live because a future commit still needs to create or
  preserve a deep-link redirect or alias for the `/admin` entry point.
- `worker_console` is covered by split Next routes: `/workspace/agents` and
  `/workspace/workers`.
- Vite `/workspace/agents` remains live until a future explicit same-path
  ownership cutover commit reruns Vite/Next browser evidence and keeps the
  Agent Gateway CLI/API/MCP contract unchanged.
- `retirement_allowed` remains `false` for both entries.

## Candidate Routes

| Matrix entry | Legacy Vite route | Canonical Next routes | Current state |
|---|---|---|---|
| `control_tower` | `/admin` | `/workspace`, `/workspace/agents`, `/workspace/governance`, `/workspace/deployment` | Candidate only; `/admin` alias still required |
| `worker_console` | `/workspace/agents` | `/workspace/agents`, `/workspace/workers` | Candidate only; future explicit same-path ownership cutover required |

## Retirement Commit Requirements

Every future retirement commit must name the exact route pair being retired,
preserve a deep-link redirect or alias, update the UI/API parity matrix, and
rerun Vite plus Next browser evidence after the route change.

The commit must keep Agent Gateway CLI/API/MCP contracts unchanged and must not
commit local databases, generated artifacts, raw prompts, raw responses, private
transcripts, or secrets.

## Verification

```bash
python3 scripts/ui_covered_route_retirement_packet_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/nextjs_control_tower_parity_smoke.py
python3 scripts/nextjs_worker_console_parity_smoke.py
python3 scripts/vite_playwright_snapshot_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
```
