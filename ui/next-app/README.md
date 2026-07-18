# AgentOps MIS Next.js Parity Track

This app is the commercial migration lane for the AgentOps MIS frontend. It is
intentionally parallel to `ui/start-building-app` until page-by-page parity is
proven.

## Run

```bash
cd ui/next-app
npm install
AGENTOPS_API_BASE=http://127.0.0.1:8765/api npm run dev
```

Most Next.js `/api/mis/*` routes still proxy to the current MIS API provider in
explicit Free Local mode; the default provider is `http://127.0.0.1:8765/api`.
Commercial production never uses the catch-all Python bridge: an unowned route
returns `typescript_route_owner_required` until it has a direct TypeScript owner.
The first backend migration
slice owns exact routes `/api/mis/agent-gateway/tasks`,
`/api/mis/agent-gateway/runs/start`, and
`/api/mis/agent-gateway/runs/[runId]/heartbeat` plus Agent Plan,
plan-evidence-manifest, tool-call, evaluation, and artifact evidence routes:
local development defaults to proxy mode,
while `AGENTOPS_DEPLOYMENT_MODE=production` defaults those routes to the
TypeScript Postgres control plane and fails closed when
`AGENTOPS_POSTGRES_DSN` is absent. `AGENTOPS_CONTROL_PLANE_MODE=proxy` is an
explicit rollback switch only with `AGENTOPS_DEPLOYMENT_MODE=local|free_local`;
`AGENTOPS_TS_CONTROL_PLANE_MODE` remains a compatibility alias. Production
Memory Review never follows either proxy switch because Human identity cannot
be downgraded to the Python compatibility actor.

```bash
AGENTOPS_DEPLOYMENT_MODE=production \
AGENTOPS_POSTGRES_DSN=postgresql://... \
npm run dev
```

## Verify

```bash
python3 scripts/nextjs_parity_smoke.py
python3 scripts/nextjs_production_python_proxy_fail_closed_smoke.py
cd ui/next-app && npm run build
python3 scripts/nextjs_agent_gateway_task_proxy_smoke.py
python3 scripts/nextjs_postgres_control_plane_tasks_smoke.py
python3 scripts/nextjs_postgres_memory_propose_smoke.py
python3 scripts/nextjs_postgres_human_memory_review_smoke.py
AGENTOPS_POSTGRES_DSN=postgresql://... npm run test:worker-task-pull-claim-contract
AGENTOPS_POSTGRES_DSN=postgresql://... npm run test:worker-gateway-direct-contract
python3 scripts/nextjs_postgres_real_worker_human_review_smoke.py \
  --postgres-dsn postgresql://...
python3 scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py
python3 scripts/nextjs_worker_dispatch_once_smoke.py
python3 scripts/nextjs_pixel_office_floor_smoke.py
python3 scripts/local_brief_prepared_action_smoke.py
python3 scripts/nextjs_local_brief_smoke.py
python3 scripts/nextjs_customer_worker_dispatch_smoke.py
python3 scripts/nextjs_customer_worker_async_job_smoke.py
python3 scripts/nextjs_customer_worker_prepared_action_smoke.py
python3 scripts/nextjs_worker_stuck_release_smoke.py
python3 scripts/nextjs_enrollment_request_smoke.py
python3 scripts/nextjs_worker_daemon_control_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture
python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture
```

## Commercial Human Session

Production direct mode owns `/api/mis/human-auth/login|session|logout`, the
workspace-scoped candidate list, and candidate approve/reject in
TypeScript/Postgres. Configure `AGENTOPS_ALLOWED_ORIGINS` and a minimum 32-byte
`AGENTOPS_HUMAN_SESSION_HMAC_KEY`; machine Agent Gateway and workspace admin
credentials cannot authorize these routes.

Apply and verify the exact schema version, then create the first Owner from a
deployment terminal:

```bash
AGENTOPS_POSTGRES_DSN=postgresql://... npm run migrate:postgres
AGENTOPS_POSTGRES_DSN=postgresql://... npm run schema:readiness
AGENTOPS_POSTGRES_DSN=postgresql://... npm run bootstrap:owner -- \
  --workspace-id acme --username owner --display-name "Workspace Owner"
```

This command is global first-deployment bootstrap only. It fails once an Owner
exists. Later user/workspace provisioning and credential lifecycle are not yet
implemented. Production ingress must also enforce a trusted-proxy-aware IP rate
limit for sign-in. Retention jobs and a precompiled bootstrap artifact remain
release blockers; see `docs/HUMAN_MEMORY_REVIEW_RELEASE_BLOCKERS.json` and
`docs/NEXTJS_POSTGRES_HUMAN_MEMORY_REVIEW_ACCEPTANCE.md`.

The Playwright smoke starts an isolated MIS API provider and Next.js dev server,
captures browser snapshots for the current parity routes, exercises approval and
memory review actions through the Next.js UI, verifies the state change through
`/api/mis/*`, and fails on token-like output.

## Parity Slices

- App Router route: `/workspace`
- App Router route: `/workspace/agents`
- App Router route: `/workspace/agents/dispatch-once`
- App Router route: `/workspace/agents/release-task`
- App Router route: `/workspace/agents/daemon-control`
- App Router route: `/workspace/agents/enrollment-request`
- App Router route: `/workspace/commercial`
- App Router route: `/workspace/governance`
- App Router route: `/workspace/deployment`
- App Router route: `/workspace/pixel-office`
- App Router route: `/workspace/pixel-office/local-brief`
- App Router route: `/workspace/dispatch`
- App Router route: `/workspace/dispatch/customer-worker`
- App Router route: `/workspace/dispatch/customer-worker-job`
- App Router route: `/workspace/evidence/[manifestId]`
- App Router route: `/workspace/tasks`
- App Router route: `/workspace/tasks/[taskId]`
- App Router route: `/workspace/runs`
- App Router route: `/workspace/runs/[runId]`
- App Router route: `/workspace/approvals`
- App Router route: `/workspace/memory`
- App Router route: `/workspace/audit`
- App Router route: `/workspace/reports`
- App Router route: `/workspace/customer-projects/[projectId]/report`
- Free Local compatibility API proxy: `/api/mis/[...path]`; commercial production
  rejects this catch-all and requires an explicit TypeScript/Postgres route owner.
- Agent Gateway task migration contract: scoped
  `GET|POST /api/mis/agent-gateway/tasks` preserves no-token, missing-scope,
  workspace, agent-binding, and short-session behavior. Production defaults to
  a TypeScript-owned Postgres transaction that writes task, runtime event, and
  compatible tamper-chain audit evidence without starting the Python API; local
  proxy mode remains the bounded rollback path. The legacy Python run-start
  rollback does not enforce the TypeScript non-mock verified-plan gate and is
  not equivalent commercial security evidence.
- Agent Gateway run-start migration contract: scoped
  `POST /api/mis/agent-gateway/runs/start` authenticates before workspace-scoped
  task lookup, prevents run-id rebinding, makes repeated/concurrent starts
  idempotent with one run/runtime/audit winner, redacts summaries before
  persistence, and audits the linked task transition to `running`.
- Agent Gateway run-heartbeat migration contract: scoped
  `POST /api/mis/agent-gateway/runs/[runId]/heartbeat` authenticates before
  workspace-scoped lookup, takes task-before-run locks, redacts persisted output,
  suppresses duplicate runtime/audit evidence for identical heartbeats, gives
  conflicting terminal heartbeats one winner, syncs terminal task/agent state,
  and rejects terminal revival.
- Agent Gateway Worker ingress migration contract: the durable
  `/api/agent-gateway/*` CLI path is rewritten by Next to direct TypeScript
  handlers for register, task pull/claim, heartbeat, and audit. Production uses
  Postgres scope/workspace/agent/run/task locks; Free Local keeps the Python
  proxy rollback path. The focused Postgres contracts prove bounded bodies,
  server-derived audit actors, sensitive metadata omission, and single-winner
  claims. `nextjs_postgres_real_worker_human_review_v1` separately proves real
  Hermes/OpenClaw execution through candidate creation and Human approval
  without starting the Python API.
- Agent Gateway execution-evidence migration contract: scoped tool-call,
  evaluation-submit, and artifact routes bind evidence to the authenticated
  workspace/run/agent, redact structured and summary data, serialize same-ID
  writes, reject evidence rewrites and tool terminal resets, and force risky
  tool calls plus their run/task into audited `waiting_approval` state.
- Agent Plan and closure migration contract: scoped agent-plan and
  plan-evidence-manifest routes authenticate before scoped lookups, serialize
  same-ID writes, keep submitted plans and manifest bindings immutable, reserve
  approval status for human control-plane decisions, require a verified plan for
  non-mock run start, and persist verified or blocked manifest outcomes with
  compatible runtime/audit evidence.
- Agent Gateway CLI worker dogfood contract: a scoped task created through
  Next `/api/mis/agent-gateway/tasks` is claimed and completed by the worker
  CLI entrypoint, then run/tool/evaluation/plan-evidence proof is read back
  through the Next proxy without leaking the raw Gateway token.
- Worker dispatch contract: the Next worker console can run one safe mock
  `POST /api/mis/workers/local/dispatch-once` through the MIS proxy and the
  `/workspace/agents/dispatch-once` form fallback; the proxy and fallback
  reject non-mock adapters with `mock_only_next_parity` before upstream
  execution.
- Pixel Office floor contract: `/workspace/pixel-office` renders a read-only
  Pixel Operating Map from dashboard, agent, task, run, approval, memory, and
  audit read models. It uses commercial-safe geometry, copies no Star Office
  assets, links zones into formal Next ledgers, and keeps live runtime execution
  disabled.
- Local brief contract: the Next Pixel Office route can dry-run
  `POST /api/mis/workflows/local-brief` through the MIS proxy and the
  `/workspace/pixel-office/local-brief` form fallback. It records prompt/state
  hashes and structured preview only, prepares approval-bound live actions
  without calling Agnesfallback, requires approval before resume, blocks hash
  mismatch/replay, and does not expose prompt bodies or token-like material.
- Customer-worker dispatch contract: the Next dispatch page can run one safe
  mock `POST /api/mis/workflows/customer-worker-task` through the MIS proxy and
  the `/workspace/dispatch/customer-worker` form fallback, read task/run/artifact
  delivery approval and verified plan-evidence back through the Next proxy,
  reject invalid adapters with `adapter_invalid`, and prepare/resume
  Hermes/OpenClaw live requests through the backend prepared-action wall. It
  also reads `/api/mis/workflows/customer-worker-prepared-actions` and renders a
  ledger-derived pending/approved queue whose resume controls use safe redacted
  `resume_form` fields instead of raw prepared-action JSON.
- Customer-worker async job contract: the Next dispatch page can submit one
  safe mock `POST /api/mis/workflows/customer-worker-task/submit` through the
  MIS proxy and the `/workspace/dispatch/customer-worker-job` form fallback,
  read the completed workflow job plus task/run/verified plan-evidence back
  through the Next proxy, reject invalid adapters with `adapter_invalid`, and
  prepare/resume Hermes/OpenClaw job submission through the backend
  prepared-action wall.
- Worker recovery contract: the Next worker console can read stuck tasks and
  release one stale running task through `POST /api/mis/workers/tasks/release`
  plus the `/workspace/agents/release-task` form fallback; the proxy rejects
  `force:true` with `force_release_not_allowed_next_parity`.
- Worker daemon contract: the Next worker console can start/restart/stop only
  the safe `mock` daemon through `POST /api/mis/workers/local/start|restart|stop`
  plus the `/workspace/agents/daemon-control` form fallback; non-mock or
  confirm/live daemon attempts are rejected before upstream execution with
  `mock_daemon_only_next_parity` and `live_worker_daemon_not_allowed_next_parity`.
- Enrollment request contract: the Next worker console can preview Agent
  Gateway enrollment policy and create approval-gated enrollment requests
  through `POST /api/mis/agent-gateway/enrollment/request` plus the
  `/workspace/agents/enrollment-request` form fallback. Raw token mint routes
  such as `create`, `issue-approved`, and `rotate` are blocked in the Next
  proxy with `enrollment_token_issue_not_allowed_next_parity`.
- Live data contract: dashboard metrics, agents, production readiness, worker readiness, tasks, runs, approvals, memories, audit, customer projects, delivery board, customer project report
- Commercial contract: edition, capability matrix, fail-closed gates, billing-call omission, and token omission load read-only through the MIS API proxy
- Governance contract: production readiness, workspace/RBAC gate state, Team `approval_policies` enrollment approval gating, short-lived session governance, and audit evidence load read-only through the MIS API proxy without raw session IDs or token material
- Deployment contract: `deployment_readiness_v1` loads local readiness, backup/restore evidence, BYOC recovery drill status, signed audit export readiness, `audit_retention_policy_v1` read-only retention preview, `audit_retention_controls_v1` cleanup-approval/legal-hold controls, SSO hooks, storage backend gates, fixed Postgres runtime write-gate readiness, and private connector policy through the MIS API proxy; restore remains CLI-confirmed and retention cleanup remains disabled
- Storage migration contract: `/workspace/deployment` reads `/api/storage/backend-status` through the Next.js server loader and surfaces SQLite default state, Postgres/BYOC prerequisites, read-only HTTP mode, write blocking, fallback omission, and the active fixed-runtime Postgres write gate when `experimental_write_http` is selected
- First-paint contract: approval and memory review queues can load on the App Router server path from the configured MIS API
- Interaction contract: approval review and memory review write through the Next.js UI, with client fetch plus Next form fallback routes, then refresh from the MIS API proxy
- Ledger detail contract: task/run detail routes are read-only, load through the MIS API proxy, and expose linked evidence rows plus token omission state
- Customer delivery contract: reports and customer project report pages load from the MIS API, surface Agent Plan / plan-evidence status, link to a read-only evidence drilldown, and report archive writes through a Next form fallback route before refreshing the report artifact evidence
- Dispatch contract: customer task templates and commercial entitlement gates load from the MIS API; template execution uses a Next form fallback and must surface Free Local `report_templates` blocking without creating a project, then create a ledger-backed project/report artifact when an isolated `pro_workspace` entitlement fixture is active. The dispatch page also supports safe mock customer-worker task/job readback plus Hermes/OpenClaw prepared-action prepare/resume controls, ledger-derived prepared-action resume queue, delivery approval, and plan-evidence proof. Pixel Office map parity and local-brief prepared-action controls live at `/workspace/pixel-office`; richer owner workflow remains canonical in Vite until later Gate 4 slices.
- Canonical predecessors:
  - `ui/start-building-app/src/app/components/pages/WorkspaceHome.tsx`
  - `ui/start-building-app/src/app/components/pages/AIEmployees.tsx`
  - `ui/start-building-app/src/app/components/pages/MyTasks.tsx`
  - `ui/start-building-app/src/app/components/pages/RunLedger.tsx`
  - `ui/start-building-app/src/app/components/pages/ApprovalsInbox.tsx`
  - `ui/start-building-app/src/app/components/pages/MemoryLibrary.tsx`
  - `ui/start-building-app/src/app/components/pages/AuditCenter.tsx`
  - `ui/start-building-app/src/app/components/pages/Reports.tsx`
  - `ui/start-building-app/src/app/components/pages/CustomerProjectReport.tsx`
  - `ui/start-building-app/src/app/components/pixel/CustomerDispatchPanel.tsx`

Do not remove the Vite app until this lane passes route, API, and visual parity
for each commercial workflow.
