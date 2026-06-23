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
| Agent detail | `agent_detail` | `covered` | Not allowed |
| Reports and delivery board | `reports` | `covered` | Not allowed |
| Approvals | `approvals` | `covered` | Not allowed |
| Memory review | `memory` | `covered` | Not allowed |
| Audit evidence | `audit` | `covered` | Not allowed |
| Customer report | `customer_project_report` | `covered` | Not allowed |
| Task and run ledgers | `task_list`, `task_detail`, `run_ledger`, `run_detail` | `covered` | Not allowed |
| Tool call ledger | `tool_calls` | `covered` | Not allowed |
| Evaluation room | `evaluation_room` | `covered` | Not allowed |
| Runtime connectors | `runtime_connectors` | `covered` | Not allowed |
| Notion external base | `external_bases_notion` | `covered` | Not allowed |

## Current Important Gaps

- Pixel Office is only partially represented in Next.js. Next currently proves
  a read-only Pixel Operating Map, template entitlement dispatch, mock-only
  customer-worker dispatch, and mock-only async customer-worker job status
  readback, but Vite remains canonical for local brief, live runtime execution,
  richer owner dispatch workflow, and final visual route retirement evidence.
- Worker console is only partially represented in Next.js. Next is read-only for
  production safety and readiness; Vite remains canonical for local worker
  start/stop/restart, task release, remote enrollment mutation, and detailed
  operator controls.
- Admin-only Vite routes for the full template/base-switching console are
  deferred. Tool calls, evaluation room, runtime connectors, Notion external
  base, and agent detail now have Next parity at `/workspace/tool-calls`,
  `/workspace/evaluations`, `/workspace/connectors`,
  `/workspace/external-bases/notion`, and `/workspace/agents/:agentId`.
- Several `covered` routes still need a route-level Vite/Next data-shape diff
  before a retirement decision. Browser snapshot evidence is necessary but not
  sufficient.
- Tool calls now have a Next read-only parity route at `/workspace/tool-calls`.
  It reads `GET /tool-calls`, exposes risk/status filtering, links each tool
  call to `/workspace/runs/:runId`, and keeps `/admin/toolcalls` canonical until
  browser evidence and route retirement are explicit.
- Evaluation Room now has a Next read-only parity route at
  `/workspace/evaluations`. It reads `GET /evaluations`, exposes score,
  pass/fail, evaluator type, agent, run, task, and created-at evidence, links
  rows to `/workspace/runs/:runId` and `/workspace/tasks/:taskId`, and keeps
  `/admin/evaluations` canonical until evaluation-case actions and route
  retirement are explicit.
- Runtime Connectors now have a Next parity route at `/workspace/connectors`.
  It reads `GET /runtime-connectors`, exposes status, trust, allow-real-run,
  require-confirm, endpoint, health, and connector-audit evidence, and writes
  trust changes through the Next `/workspace/connectors/trust` fallback to
  `POST /runtime-connectors/:id/trust`. `/admin/connectors` remains canonical
  until browser evidence and route retirement are explicit.
- Notion External Base now has a Next parity route at
  `/workspace/external-bases/notion`. It reads live Notion status and preview
  data through `/api/mis/integrations/notion/*`, exposes dry-run default,
  writeback blocking, connector state, preview-only report evidence, and token
  omission copy, runs dry-run export safely, and verifies Free Local blocks
  confirmed export for `notion_confirmed_export`. `/admin/bases/notion`
  remains canonical until prepared-action resume UX and route retirement are
  explicit.
- Agent Detail now has a Next parity route at `/workspace/agents/:agentId`.
  It reads `GET /agents/:id/performance`, exposes the agent profile, success
  rate, failures, approval count, budget usage, allowed tools, recent error
  groups, and recent run/task links. `/admin/agents/:id` remains canonical until
  worker console mutations and route retirement are explicit.
- Task and run list/detail now have first route-level evidence:
  `python3 scripts/ui_task_run_route_parity_smoke.py`
  (`ui_task_run_route_parity_v1`) checks Next list links to detail routes and
  compares direct MIS API task/run list/detail/graph read models with the Next
  `/api/mis/*` proxy. `python3 scripts/vite_playwright_snapshot_smoke.py`
  (`vite_browser_snapshot_parity_v1`) now also opens seeded Vite task/run detail
  routes and checks the related task/run IDs plus evidence sections.
  `python3 scripts/ui_route_naming_decision_smoke.py`
  (`ui_route_naming_decision_v1`) records `/workspace` as the future commercial
  namespace for task/run routes while keeping `/admin` as legacy compatibility;
  the human and machine-readable decision live in
  `docs/UI_ROUTE_NAMING_DECISION.md` and
  `docs/UI_ROUTE_NAMING_DECISION.json`. `python3
  scripts/ui_legacy_route_alias_smoke.py` (`ui_legacy_route_alias_v1`) verifies
  Next.js `/admin` task/run deep links redirect to the `/workspace` target
  routes. `python3 scripts/ui_navigation_inventory_smoke.py`
  (`ui_navigation_inventory_v1`) verifies Next primary task/run navigation uses
  `/workspace` and treats `/admin` task/run routes as redirect aliases only.
  `python3 scripts/ui_route_retirement_packet_smoke.py`
  (`ui_route_retirement_packet_v1`) prepares the candidate retirement packet
  while keeping `retirement_allowed: false`. Retirement still needs an explicit
  route retirement commit for each route pair.

## Verification Stack

Use this order when advancing Gate 4:

```bash
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/ui_task_run_route_parity_smoke.py
python3 scripts/ui_route_naming_decision_smoke.py
python3 scripts/ui_legacy_route_alias_smoke.py
python3 scripts/ui_navigation_inventory_smoke.py
python3 scripts/ui_route_retirement_packet_smoke.py
python3 scripts/nextjs_parity_smoke.py
cd ui/start-building-app && npm run build
cd ui/next-app && npm run build
python3 scripts/nextjs_agent_gateway_task_proxy_smoke.py
python3 scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py
python3 scripts/nextjs_worker_dispatch_once_smoke.py
python3 scripts/nextjs_pixel_office_floor_smoke.py
python3 scripts/nextjs_customer_worker_dispatch_smoke.py
python3 scripts/nextjs_customer_worker_async_job_smoke.py
python3 scripts/nextjs_worker_stuck_release_smoke.py
python3 scripts/nextjs_enrollment_request_smoke.py
python3 scripts/nextjs_worker_daemon_control_smoke.py
python3 scripts/vite_playwright_snapshot_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
```

The matrix smoke is static and fast. Browser smokes are still required for
actual UI evidence.

`python3 scripts/nextjs_agent_gateway_task_proxy_smoke.py`
(`nextjs_agent_gateway_task_proxy_v1`) starts isolated MIS API and Next.js
servers, then proves `POST /api/mis/agent-gateway/tasks` preserves the Gateway
task-create contract: no token stays `401`, missing `tasks:create` stays `403`,
workspace/agent impersonation stays blocked, valid scoped tokens create and
read back a task through the Next proxy, and direct MIS readback matches the
Next proxy response without token leakage.

`python3 scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py`
(`nextjs_agent_gateway_cli_worker_dogfood_v1`) starts isolated MIS API and
Next.js servers, creates a scoped Agent Gateway task through
`POST /api/mis/agent-gateway/tasks`, runs the worker CLI entrypoint once with
the scoped token, then reads the completed task, run/tool/evaluation evidence,
and verified plan-evidence manifest back through the Next proxy without raw
token leakage.

`python3 scripts/nextjs_worker_dispatch_once_smoke.py`
(`nextjs_worker_dispatch_once_v1`) starts isolated MIS API and Next.js servers,
sets `AGENTOPS_BASE_URL` so the worker subprocess writes into the isolated
ledger, then proves `POST /api/mis/workers/local/dispatch-once` and the Next
`/workspace/agents/dispatch-once` form fallback can run one safe `mock` worker,
persist task/run/plan-evidence proof, read the completed task back without
token leakage, and reject non-mock proxy/form dispatch before upstream
execution with `mock_only_next_parity`.

`python3 scripts/nextjs_pixel_office_floor_smoke.py`
(`nextjs_pixel_office_floor_v1`) starts isolated MIS API and Next.js servers,
opens `/workspace/pixel-office`, verifies the read-only Pixel Operating Map,
commercial-safe geometry, no-Star-Office asset boundary, live-runtime-disabled
proof, core zone routing links, and live MIS proxy readback for agents, tasks,
and runs without token leakage.

`python3 scripts/nextjs_customer_worker_dispatch_smoke.py`
(`nextjs_customer_worker_dispatch_v1`) starts isolated MIS API and Next.js
servers, proves `POST /api/mis/workflows/customer-worker-task` plus the Next
`/workspace/dispatch/customer-worker` form fallback can run one safe `mock`
customer-worker task, read task/run/delivery-approval/verified plan-evidence
back through the Next proxy, render the dispatch evidence strip, and reject
Hermes/OpenClaw before upstream execution with
`customer_worker_mock_only_next_parity`.

`python3 scripts/nextjs_customer_worker_async_job_smoke.py`
(`nextjs_customer_worker_async_job_v1`) starts isolated MIS API and Next.js
servers, proves `POST /api/mis/workflows/customer-worker-task/submit` plus the
Next `/workspace/dispatch/customer-worker-job` form fallback can submit one
safe `mock` async customer-worker job, read the completed workflow job and
task/run/verified plan-evidence back through the Next proxy, render the async
job list on `/workspace/dispatch`, and reject Hermes/OpenClaw before job
creation with `customer_worker_mock_only_next_parity`.

`python3 scripts/nextjs_worker_stuck_release_smoke.py`
(`nextjs_worker_stuck_release_v1`) starts isolated MIS API and Next.js servers,
creates stale running worker tasks, proves Next `/api/mis/workers/stuck-tasks`
can read them, proves Next `/api/mis/workers/tasks/release` returns one task to
`planned` and blocks the linked running run as `WorkerTaskReleased`, proves the
`/workspace/agents/release-task` form fallback performs the same recovery, and
proves `force:true` is rejected at the Next proxy with
`force_release_not_allowed_next_parity`.

`python3 scripts/nextjs_worker_daemon_control_smoke.py`
(`nextjs_worker_daemon_control_v1`) starts isolated MIS API and Next.js
servers, proves Next `/api/mis/workers/local/start|restart|stop` can control
the safe `mock` daemon, proves `/workspace/agents/daemon-control` form fallback
can start/restart/stop the same daemon, and proves non-mock or confirm/live
daemon attempts fail closed with `mock_daemon_only_next_parity` and
`live_worker_daemon_not_allowed_next_parity`.

`python3 scripts/nextjs_enrollment_request_smoke.py`
(`nextjs_enrollment_request_v1`) starts isolated MIS API and Next.js servers,
proves Next `/api/mis/agent-gateway/enrollment/policy-preview` is read-only,
proves invalid scopes are rejected by the Next guard before backend filtering,
proves direct raw-token mint routes such as enrollment `create` and
`issue-approved` fail closed with `enrollment_token_issue_not_allowed_next_parity`,
and proves `/api/mis/agent-gateway/enrollment/request` plus the
`/workspace/agents/enrollment-request` form fallback create pending approval
requests without minting or leaking an Agent Gateway token.
