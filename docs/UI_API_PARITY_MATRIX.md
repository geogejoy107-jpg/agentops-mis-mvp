# UI/API Parity Matrix

This document is the human-readable Gate 4 checklist. The machine-readable
contract lives in `docs/UI_API_PARITY_MATRIX.json` and is verified by:

```bash
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/ui_covered_route_retirement_packet_smoke.py
```

Contract: `ui_api_parity_matrix_v1`

## Purpose

Gate 4 prevents the Next.js track from becoming a product regression. Vite/React
remains the canonical UI until a route has explicit evidence that the Next.js
route preserves the same MIS API semantics, visible workflow, safety boundaries,
and browser behavior.

The matrix is not a blanket retirement approval. `task_detail`, `run_ledger`,
and `run_detail` now have an explicit `executed_workspace_redirect`
retirement: Vite primary links use `/workspace`, and the old Vite `/admin`
task/run routes are redirect-only deep links. Every other entry remains
`retirement_allowed: false` until a future explicit decision passes browser
smokes and route-level API/read-model diffs.

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
| Control tower | `control_tower` | `covered` | Not allowed |
| Customer dispatch / Pixel Office | `pixel_office_and_dispatch` | `covered` | Not allowed |
| Worker console | `worker_console` | `covered` | Not allowed |
| Agent detail | `agent_detail` | `covered` | Not allowed |
| Reports and delivery board | `reports` | `covered` | Not allowed |
| Approvals | `approvals` | `covered` | Not allowed |
| Memory review | `memory` | `covered` | Not allowed |
| Audit evidence | `audit` | `covered` | Not allowed |
| Customer report | `customer_project_report` | `covered` | Not allowed |
| Task and run ledgers | `task_list`, `task_detail`, `run_ledger`, `run_detail` | `covered` | `task_detail`, `run_ledger`, and `run_detail` executed to workspace redirects |
| Tool call ledger | `tool_calls` | `covered` | Not allowed |
| Evaluation room | `evaluation_room` | `covered` | Not allowed |
| Runtime connectors | `runtime_connectors` | `covered` | Not allowed |
| Notion external base | `external_bases_notion` | `covered` | Not allowed |

## Current Important Gaps

- Human Supervision reads now have direct Next/Postgres owners for dashboard
  metrics, task and run lists/details, run graph, approvals, audit, evaluations,
  and tool calls. The machine matrix records each `/api/mis/*` handler under its
  existing Workspace capability. Python remains the Free Local and explicit
  rollback path; these additions do not independently authorize Vite route
  retirement.
- Fifteen exact Agent Gateway routes now form a `next_only` TypeScript/Postgres
  control-plane slice: Worker registration and heartbeat, task pull/claim/list
  and create, Agent Plan, run lifecycle, tool/evaluation/artifact/audit,
  plan-evidence, candidate-memory, and customer-delivery approval writes.
  Production defaults these routes to Postgres and fails closed without a DSN;
  Python is retained for Free Local and the explicit per-route rollback. The
  `nextjs_postgres_control_plane_tasks_v1` smoke starts Next.js plus real
  Postgres with no Python API process and verifies authentication, workspace
  isolation, immutable IDs, concurrent single winners, redaction, Plan-gated
  non-mock execution, manifest closure, and the shared audit chain. This does
  not retire a Vite route or declare the remaining broad proxy migrated. The
  real Worker acceptance additionally requires Hermes and OpenClaw to request
  `customer_delivery` review through the production Agent Gateway owner after
  verified non-dry-run evidence, before Human Session approval.
- Pixel Office / Dispatch now has explicit visual retirement evidence in
  `pixel_office_dispatch_retirement_evidence_v1`. Next proves a read-only Pixel
  Operating Map, the owner dispatch workflow route bridge, owner task dry-run,
  template async job form fallback, local-brief prepared-action exact resume
  with approval before live Agnesfallback execution, template entitlement
  dispatch, safe mock customer-worker dispatch/readback, Hermes/OpenClaw
  customer-worker prepared-action exact resume, and ledger-derived resume
  readback. Vite remains canonical until an explicit route retirement commit
  preserves `/workspace/pixel-office` deep links and reruns browser evidence.
- Control Tower is now covered by split Next.js routes instead of a single
  Vite `/admin` replacement. `/workspace` renders live `/dashboard/metrics`
  cockpit readback with runtime health, OpenClaw import, task status, cost
  leader, failure-rate, cost, memory, and approval KPIs; `/workspace/agents`
  carries the agent performance drilldown from `GET /agents`;
  `/workspace/governance` renders production, RBAC, session, and audit
  evidence; and `/workspace/deployment` renders BYOC storage, backup, retention,
  signed export, and connector-policy gates. Vite `/admin` remains until an
  explicit route retirement commit preserves deep links, reruns browser
  evidence, and keeps Agent Gateway CLI/API/MCP unchanged.
- Worker console is now covered by split Next.js routes. `/workspace/agents`
  renders agent registry, production security, safe mock worker dispatch, mock
  daemon controls, stuck-task release, approval-gated enrollment request, and
  Agent Gateway session hygiene readback. `/workspace/workers` proves worker
  status, `/workers/fleet` lane readback, `/workers/fleet/hygiene` read-only
  cleanup preview, adapter readiness, local readiness, safe Agent Gateway
  session refs, `/operator/execution-mode` read-only adapter route/confirm-run
  and prepared-action wall readback, plus a visible Worker Console coverage
  boundary. Agent Gateway CLI/API/MCP remains canonical for token
  issue/rotate/revoke, session lifecycle, live daemon lifecycle, live dispatch
  controls, cleanup mutation, and detailed operator mutation. Vite
  `/workspace/agents` route retirement remains blocked until an explicit route
  retirement commit preserves deep links, reruns browser evidence, and keeps
  Agent Gateway CLI/API/MCP unchanged.
- Control Tower and Worker Console covered-route retirement candidates now live
  in `docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json`
  (`ui_covered_route_retirement_packet_v1`). This packet is candidate-only:
  it does not retire any Vite route, keeps `retirement_allowed: false`, and
  requires a future route-pair commit to preserve deep links, rerun Vite/Next
  browser evidence, and keep Agent Gateway CLI/API/MCP unchanged.
- Template/base switching, tool calls, evaluation room, runtime connectors,
  Notion external base, audit, and agent detail now execute workspace redirect
  retirement in Vite: primary links use `/workspace/templates`,
  `/workspace/tool-calls`, `/workspace/evaluations`, `/workspace/connectors`,
  `/workspace/external-bases/notion`, `/workspace/audit`, and
  `/workspace/agents/:agentId`, while the legacy `/admin` routes remain
  redirect-only deep links.
- Several `covered` routes still need a route-level Vite/Next data-shape diff
  before a retirement decision. Browser snapshot evidence is necessary but not
  sufficient.
- Tool calls now have a Next read-only parity route at `/workspace/tool-calls`.
  It reads `GET /tool-calls`, exposes risk/status filtering, links each tool
  call to `/workspace/runs/:runId`, and Vite `/admin/toolcalls` redirects to
  `/workspace/tool-calls`.
- Evaluation Room now has a Next read-only parity route at
  `/workspace/evaluations`. It reads `GET /evaluations`, exposes score,
  pass/fail, evaluator type, agent, run, task, and created-at evidence, links
  rows to `/workspace/runs/:runId` and `/workspace/tasks/:taskId`, and Vite
  `/admin/evaluations` redirects to `/workspace/evaluations`.
- Runtime Connectors now have a Next parity route at `/workspace/connectors`.
  It reads `GET /runtime-connectors`, exposes status, trust, allow-real-run,
  require-confirm, endpoint, health, and connector-audit evidence, and writes
  trust changes through the Next `/workspace/connectors/trust` fallback to
  `POST /runtime-connectors/:id/trust`. Vite `/admin/connectors` redirects to
  `/workspace/connectors`.
- Notion External Base now has a Next parity route at
  `/workspace/external-bases/notion`. It reads live Notion status and preview
  data through `/api/mis/integrations/notion/*`, exposes dry-run default,
  writeback blocking, connector state, preview-only report evidence, and token
  omission copy, runs dry-run export safely, and verifies Free Local blocks
  confirmed export for `notion_confirmed_export`. Vite `/admin/bases/notion`
  redirects to `/workspace/external-bases/notion`.
- Agent Detail now has a Next parity route at `/workspace/agents/:agentId`.
  It reads `GET /agents/:id/performance`, exposes the agent profile, success
  rate, failures, approval count, budget usage, allowed tools, recent error
  groups, and recent run/task links. Vite `/admin/agents/:id` redirects to
  `/workspace/agents/:id`.
- Task and run list/detail now have executed route-retirement evidence:
  `python3 scripts/ui_task_run_route_parity_smoke.py`
  (`ui_task_run_route_parity_v1`) checks Next list links to detail routes and
  compares direct MIS API task/run list/detail/graph read models with the Next
  `/api/mis/*` proxy. `python3 scripts/vite_playwright_snapshot_smoke.py`
  (`vite_browser_snapshot_parity_v1`) now opens seeded Vite task/run detail
  routes under `/workspace` and checks the related task/run IDs plus evidence
  sections; it also keeps `/admin` task/run deep-link redirect coverage.
  `python3 scripts/ui_route_naming_decision_smoke.py`
  (`ui_route_naming_decision_v1`) records `/workspace` as the commercial
  namespace for task/run and admin operations routes while making retired
  `/admin` routes redirect-only compatibility;
  the human and machine-readable decision live in
  `docs/UI_ROUTE_NAMING_DECISION.md` and
  `docs/UI_ROUTE_NAMING_DECISION.json`. `python3
  scripts/ui_legacy_route_alias_smoke.py` (`ui_legacy_route_alias_v1`) verifies
  Next.js `/admin` task/run deep links redirect to the `/workspace` target
  routes. `python3 scripts/ui_navigation_inventory_smoke.py`
  (`ui_navigation_inventory_v1`) verifies Next and Vite primary navigation use
  `/workspace` and treats retired `/admin` routes as redirect aliases only.
  `python3 scripts/ui_route_retirement_packet_smoke.py`
  (`ui_route_retirement_packet_v1`) verifies the task/run and admin-operations
  `/admin` routes are retired to workspace redirect aliases while Agent Gateway
  CLI/API/MCP remains unchanged. `python3
  scripts/ui_admin_operations_route_retirement_smoke.py`
  (`ui_admin_operations_route_retirement_v1`) verifies the admin-operations
  route set specifically.

## Verification Stack

Use this order when advancing Gate 4:

```bash
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/ui_task_run_route_parity_smoke.py
python3 scripts/ui_route_naming_decision_smoke.py
python3 scripts/ui_legacy_route_alias_smoke.py
python3 scripts/ui_navigation_inventory_smoke.py
python3 scripts/ui_route_retirement_packet_smoke.py
python3 scripts/ui_admin_operations_route_retirement_smoke.py
python3 scripts/ui_covered_route_retirement_packet_smoke.py
python3 scripts/pixel_office_dispatch_retirement_evidence_smoke.py
python3 scripts/nextjs_parity_smoke.py
python3 scripts/nextjs_postgres_control_plane_tasks_smoke.py
cd ui/start-building-app && npm run build
cd ui/next-app && npm run build
python3 scripts/nextjs_agent_gateway_task_proxy_smoke.py
python3 scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py
python3 scripts/nextjs_worker_dispatch_once_smoke.py
python3 scripts/nextjs_pixel_office_floor_smoke.py
python3 scripts/nextjs_pixel_office_dispatch_smoke.py
python3 scripts/nextjs_control_tower_parity_smoke.py
python3 scripts/local_brief_prepared_action_smoke.py
python3 scripts/nextjs_local_brief_smoke.py
python3 scripts/nextjs_customer_worker_dispatch_smoke.py
python3 scripts/nextjs_customer_worker_async_job_smoke.py
python3 scripts/nextjs_customer_worker_prepared_action_smoke.py
python3 scripts/nextjs_worker_stuck_release_smoke.py
python3 scripts/nextjs_enrollment_request_smoke.py
python3 scripts/nextjs_worker_gateway_lifecycle_guard_smoke.py
python3 scripts/nextjs_worker_daemon_control_smoke.py
python3 scripts/nextjs_worker_console_parity_smoke.py
python3 scripts/operator_execution_mode_smoke.py
python3 scripts/nextjs_template_switching_smoke.py
python3 scripts/vite_playwright_snapshot_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
```

The matrix smoke is static and fast. Browser smokes are still required for
actual UI evidence.

`python3 scripts/pixel_office_dispatch_retirement_evidence_smoke.py`
(`pixel_office_dispatch_retirement_evidence_v1`) records the Pixel Office /
Dispatch route pair as visually evidenced but not retired. It verifies Vite
still owns `/workspace/pixel-office`, Next has `/workspace/pixel-office` plus
Dispatch form fallbacks, browser evidence names both surfaces, omission rules
stay fail-closed, and any future retirement still needs an explicit commit.

`python3 scripts/ui_covered_route_retirement_packet_smoke.py`
(`ui_covered_route_retirement_packet_v1`) records Control Tower and Worker
Console as covered-route retirement candidates without retiring Vite. It
verifies Vite `/admin` and `/workspace/agents` still exist, Next owns the
canonical split routes, the matrix remains `retirement_allowed: false`, and any
future route change still needs an explicit route-pair commit with deep-link
compatibility and rerun browser evidence.

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

`python3 scripts/nextjs_pixel_office_dispatch_smoke.py`
(`nextjs_pixel_office_dispatch_v1`) starts isolated Pro MIS API and Next.js
servers, proves `/workspace/pixel-office` exposes the owner dispatch workflow
bridge, then exercises `/workspace/dispatch/customer-task` and
`/workspace/dispatch/template-job` form fallbacks with team/risk/priority
forwarding and Next proxy task/job readback without token leakage.

`python3 scripts/nextjs_control_tower_parity_smoke.py`
(`nextjs_control_tower_parity_v1`) starts isolated MIS API and Next.js servers,
verifies `/workspace` split proof plus `/api/mis/dashboard/metrics`,
`/api/mis/agents`, `/api/mis/security/production-readiness`,
`/api/mis/local/readiness`, `/api/mis/storage/backend-status`, and
`/api/mis/commercial/entitlements`, proves Free Local keeps the
`approval_policies` enrollment gate fail-closed, opens `/workspace`,
`/workspace/agents`, `/workspace/governance`, and `/workspace/deployment`, and
checks the transcript for token-like leakage.

`python3 scripts/nextjs_local_brief_smoke.py` (`nextjs_local_brief_v1`) starts
isolated MIS API and Next.js servers, proves the Next
`/api/mis/workflows/local-brief` proxy allows dry-run local brief plans with
prompt/state hashes and no prompt body, prepares approval-bound live actions
without calling Agnesfallback, requires approval before resume, blocks hash
mismatch and replay, consumes the prepared action after one live fake-provider
call, and proves the `/workspace/pixel-office/local-brief` form fallback
reports dry-run, waiting-approval, and live-run states without token leakage.

`python3 scripts/local_brief_prepared_action_smoke.py`
(`local_brief_prepared_action_v1`) locks the backend contract directly:
confirmed local brief creates `prepared_actions`, `approvals`, run/tool evidence
and a structured state snapshot under `AGENTOPS_RUNTIME_DIR`; approval alone
does not call the provider; exact resume calls Agnesfallback once, stores only
summary/hash evidence, and replay is blocked.

`python3 scripts/nextjs_customer_worker_dispatch_smoke.py`
(`nextjs_customer_worker_dispatch_v1`) starts isolated MIS API and Next.js
servers, proves `POST /api/mis/workflows/customer-worker-task` plus the Next
`/workspace/dispatch/customer-worker` form fallback can run one safe `mock`
customer-worker task, read task/run/delivery-approval/verified plan-evidence
back through the Next proxy, render the dispatch evidence strip, and reject
invalid adapters before upstream execution with `adapter_invalid`.

`python3 scripts/nextjs_customer_worker_async_job_smoke.py`
(`nextjs_customer_worker_async_job_v1`) starts isolated MIS API and Next.js
servers, proves `POST /api/mis/workflows/customer-worker-task/submit` plus the
Next `/workspace/dispatch/customer-worker-job` form fallback can submit one
safe `mock` async customer-worker job, read the completed workflow job and
task/run/verified plan-evidence back through the Next proxy, render the async
job list on `/workspace/dispatch`, and reject invalid adapters before job
creation with `adapter_invalid`.

`python3 scripts/nextjs_customer_worker_prepared_action_smoke.py`
(`nextjs_customer_worker_prepared_action_v1`) starts a monkeypatched isolated
MIS API provider plus Next.js, proves Hermes/OpenClaw customer-worker sync and
async requests pass through the Next proxy into the backend prepared-action
wall, require approval before resume, block request-hash mismatch and replay,
and load `GET /api/mis/workflows/customer-worker-prepared-actions` so Dispatch
can render a ledger-derived pending/approved queue with safe redacted
`resume_form` fields. The readback exposes only IDs, adapter, sync/async flag,
approval decision, request hashes, status/result ids, and omission flags; it
must not expose raw `normalized_args_json`, `result_json`, `snapshot_ref`,
prompts, responses, credentials, tokens, or private transcripts.

`python3 scripts/nextjs_worker_stuck_release_smoke.py`
(`nextjs_worker_stuck_release_v1`) starts isolated MIS API and Next.js servers,
creates stale running worker tasks, proves Next `/api/mis/workers/stuck-tasks`
can read them, proves Next `/api/mis/workers/tasks/release` returns one task to
`planned` and blocks the linked running run as `WorkerTaskReleased`, proves the
`/workspace/agents/release-task` form fallback performs the same recovery, and
proves `force:true` is rejected at the Next proxy with
`force_release_not_allowed_next_parity`.

`python3 scripts/nextjs_worker_gateway_lifecycle_guard_smoke.py`
(`nextjs_worker_gateway_lifecycle_guard_v1`) starts isolated MIS API and
Next.js servers, creates a real backend enrollment/session as setup proof that
the backend can emit one-time session tokens, then proves the Next `/api/mis`
proxy blocks `session/create`, `session/revoke`, and `enrollment/revoke` with
`gateway_lifecycle_write_not_allowed_next_parity`. It also verifies
`/workspace/agents` renders only session hygiene readback with token/session
omission proof.

`python3 scripts/nextjs_worker_daemon_control_smoke.py`
(`nextjs_worker_daemon_control_v1`) starts isolated MIS API and Next.js
servers, proves Next `/api/mis/workers/local/start|restart|stop` can control
the safe `mock` daemon, proves `/workspace/agents/daemon-control` form fallback
can start/restart/stop the same daemon, and proves non-mock or confirm/live
daemon attempts fail closed with `mock_daemon_only_next_parity` and
`live_worker_daemon_not_allowed_next_parity`.

`python3 scripts/nextjs_worker_console_parity_smoke.py`
(`nextjs_worker_console_parity_v1`) starts isolated MIS API and Next.js
servers, opens `/workspace/workers`, verifies `/api/mis/workers/fleet`,
`/api/mis/workers/fleet/hygiene`, and safe session readback stay token/session
redacted and read-only, and proves the focused Worker Console shows fleet,
hygiene, adapter readiness, session hygiene, and fail-closed lifecycle boundary
evidence, the Worker Console coverage boundary, Agent Gateway CLI/API/MCP
canonical lifecycle ownership, and `/operator/execution-mode` readback without
executing live work.

`python3 scripts/operator_execution_mode_smoke.py`
(`operator_execution_mode_v1`) verifies `GET /api/operator/execution-mode`
and `agentops operator execution-mode` expose the same read-only adapter route,
confirm-run wall, prepared-action wall, pending approval/job counts, and
omission proof without mutating SQLite, starting daemons, or executing live
adapters.

`python3 scripts/nextjs_template_switching_smoke.py`
(`nextjs_template_switching_parity_v1`) starts isolated MIS API and Next.js
servers, opens `/workspace/templates`, verifies `/api/mis/template-packages`,
`/api/mis/template-bindings`, `/api/mis/bases`, and
`/api/mis/migration/preview`, exercises the migration-preview form fallback,
and checks the template/base switching transcript for token-like leakage.

`python3 scripts/nextjs_enrollment_request_smoke.py`
(`nextjs_enrollment_request_v1`) starts isolated MIS API and Next.js servers,
proves Team Governance entitlement readback enables `approval_policies` on
`/workspace/governance`, proves Next
`/api/mis/agent-gateway/enrollment/policy-preview` is read-only,
proves invalid scopes are rejected by the Next guard before backend filtering,
proves direct raw-token mint routes such as enrollment `create` and
`issue-approved` fail closed with `enrollment_token_issue_not_allowed_next_parity`,
and proves `/api/mis/agent-gateway/enrollment/request` plus the
`/workspace/agents/enrollment-request` form fallback create pending approval
requests without minting or leaking an Agent Gateway token.
