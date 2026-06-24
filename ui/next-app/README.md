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

The Next.js API route `/api/mis/*` proxies to the current MIS API provider. The
default provider is `http://127.0.0.1:8765/api`.

## Verify

```bash
python3 scripts/nextjs_parity_smoke.py
cd ui/next-app && npm run build
python3 scripts/nextjs_agent_gateway_task_proxy_smoke.py
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
```

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
- Runtime API proxy: `/api/mis/[...path]`
- Agent Gateway task proxy contract: scoped `POST /api/mis/agent-gateway/tasks`
  preserves no-token, missing-scope, workspace, and agent-binding failures
  before allowing task creation through the configured MIS provider
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
  Hermes/OpenClaw live requests through the backend prepared-action wall.
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
- Governance contract: production readiness, workspace/RBAC gate state, short-lived session governance, and audit evidence load read-only through the MIS API proxy without raw session IDs
- Deployment contract: `deployment_readiness_v1` loads local readiness, backup/restore evidence, BYOC recovery drill status, signed audit export readiness, `audit_retention_policy_v1` read-only retention preview, `audit_retention_controls_v1` cleanup-approval/legal-hold controls, SSO hooks, storage backend gates, and private connector policy through the MIS API proxy; restore remains CLI-confirmed and retention cleanup remains disabled
- Storage migration contract: `/workspace/deployment` reads `/api/storage/backend-status` through the Next.js server loader and surfaces SQLite default state, Postgres/BYOC prerequisites, read-only HTTP mode, write blocking, fallback omission, and the next required parity proof
- First-paint contract: approval and memory review queues can load on the App Router server path from the configured MIS API
- Interaction contract: approval review and memory review write through the Next.js UI, with client fetch plus Next form fallback routes, then refresh from the MIS API proxy
- Ledger detail contract: task/run detail routes are read-only, load through the MIS API proxy, and expose linked evidence rows plus token omission state
- Customer delivery contract: reports and customer project report pages load from the MIS API, surface Agent Plan / plan-evidence status, link to a read-only evidence drilldown, and report archive writes through a Next form fallback route before refreshing the report artifact evidence
- Dispatch contract: customer task templates and commercial entitlement gates load from the MIS API; template execution uses a Next form fallback and must surface Free Local `report_templates` blocking without creating a project, then create a ledger-backed project/report artifact when an isolated `pro_workspace` entitlement fixture is active. The dispatch page also supports safe mock customer-worker task/job readback plus Hermes/OpenClaw prepared-action prepare/resume controls with delivery approval and plan-evidence proof. Pixel Office map parity and local-brief prepared-action controls live at `/workspace/pixel-office`; richer owner workflow remains canonical in Vite until later Gate 4 slices.
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
