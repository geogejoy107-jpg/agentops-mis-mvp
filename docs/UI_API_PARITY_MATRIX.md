# UI/API Parity Matrix

This document is the human-readable Gate 4 checklist. The machine-readable
contract lives in `docs/UI_API_PARITY_MATRIX.json` and is verified by:

```bash
python3 scripts/ui_api_parity_matrix_smoke.py
```

Contract: `ui_api_parity_matrix_v1`

## Purpose

Gate 4 prevents the Next.js track from becoming a product regression. Vite/React
remains the canonical UI until a route has explicit evidence that the Next.js
route preserves the same MIS API semantics, visible workflow, safety boundaries,
and browser behavior.

The matrix is not a retirement approval. Every entry currently has
`retirement_allowed: false`. Retiring a Vite route requires a future explicit
decision after both browser smokes and route-level API/read-model diffs pass.

## Status Values

| Status | Meaning |
| --- | --- |
| `covered` | A Next route exists for the same user capability and current evidence covers the main read/action path. Retirement still needs an explicit decision. |
| `partial` | Next covers only part of the Vite capability or intentionally read-only parity. The Vite route remains canonical for the missing behavior. |
| `next_only` | New commercial/BYOC/Next migration surface that does not replace a Vite route. |
| `deferred` | Vite-only route intentionally left for a later Gate 4 slice. |

## Gate 4 Required Capabilities

These capabilities must be covered in both UIs or explicitly deferred before any
route retirement:

| Capability | Matrix ID | Current status | Retirement state |
| --- | --- | --- | --- |
| Customer dispatch / Pixel Office | `pixel_office_and_dispatch` | `partial` | Not allowed |
| Worker console | `worker_console` | `partial` | Not allowed |
| Reports and delivery board | `reports` | `covered` | Not allowed |
| Approvals | `approvals` | `covered` | Not allowed |
| Memory review | `memory` | `covered` | Not allowed |
| Audit evidence | `audit` | `covered` | Not allowed |
| Customer report | `customer_project_report` | `covered` | Not allowed |
| Task and run ledgers | `task_list`, `task_detail`, `run_ledger`, `run_detail` | `covered` | Not allowed |

## Current Important Gaps

- Pixel Office is only partially represented in Next.js. Next currently proves
  template entitlement dispatch, but Vite remains canonical for the visual map,
  local brief, customer-worker dispatch form, async job status, and richer owner
  dispatch workflow.
- Worker console is only partially represented in Next.js. Next is read-only for
  production safety and readiness; Vite remains canonical for local worker
  start/stop/restart, task release, remote enrollment mutation, and detailed
  operator controls.
- Admin-only Vite routes for evaluations, tool calls, connectors, external
  bases, per-agent performance, and the full template/base-switching console are
  deferred.
- Several `covered` routes still need a route-level Vite/Next data-shape diff
  before a retirement decision. Browser snapshot evidence is necessary but not
  sufficient.
- Task and run detail pages exist in Next.js, but list-row navigation parity is
  still incomplete. Vite task/run lists link directly into their detail routes;
  Next detail pages are currently proven through the evidence drilldown smoke.

## Verification Stack

Use this order when advancing Gate 4:

```bash
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/nextjs_parity_smoke.py
cd ui/start-building-app && npm run build
cd ui/next-app && npm run build
python3 scripts/vite_playwright_snapshot_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
```

The matrix smoke is static and fast. Browser smokes are still required for
actual UI evidence.
