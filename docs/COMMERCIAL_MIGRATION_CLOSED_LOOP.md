# Commercial Migration Closed Loop

## Final Target

AgentOps MIS should become a commercial-ready, local-first and BYOC-capable AI
workforce control plane without breaking the current working product line.

The target state is:

- Humans use the browser workspace/admin console for dispatch, supervision,
  approval, delivery review, memory review, and operations.
- Agents use Agent Gateway CLI/API/MCP for execution and evidence writeback.
- The Python control plane remains valid until a replacement passes parity
  gates. There is no big-bang rewrite.
- SQLite remains the default Free Local ledger. Postgres is introduced through a
  storage boundary for Team Governance and Enterprise/BYOC.
- Vite/React remains the current canonical product UI. `ui/next-app` is the
  parallel Next.js App Router migration track; it starts with the workspace
  cockpit and `/api/mis/*` proxy, then replaces routes only after the UI/API
  parity gate is green.
- Commercial release status is also exposed through read-only
  `/api/commercial/release-status` and rendered on Next `/workspace/commercial`
  so release promotion, exact-head CI, and current-evidence blockers are visible
  in the migration track without running network, live runtime, or billing calls
  during page load. Operators can explicitly request external exact-head CI
  readback with `?exact_head_ci=1` / `?include_external_ci_evidence=1`; that
  readback is still read-only and must not flip release, handoff, or merge gates.
- Commercial release replaces demo-only visual assets with original Pixel Office
  assets and keeps Star-Office assets out of public/commercial distribution.
- Every migration step has a reversible branch, a named verification command,
  and a rollback path.

## Closed Loop

Each commercial migration increment follows the same loop:

```text
Frame -> Slice -> Implement -> Verify -> Record -> Integrate -> Reassess
```

| Step | Required output | Stop condition |
| --- | --- | --- |
| Frame | One user/business capability and one technical boundary | The slice needs secrets, hosted infra, or asset rights that are not available |
| Slice | A branch/worktree with owned files and conflict rules | The slice rewrites shared contracts without a parity test |
| Implement | Small docs/code/schema changes behind current behavior | The change breaks local-first demo or Agent Gateway execution |
| Verify | Readiness/smoke command output and `git diff --check` | Token-like material, local DBs, `dist`, or `node_modules` appear in the diff |
| Record | README/docs/runbook update with evidence and remaining gaps | The evidence cannot be reproduced from a clean clone |
| Integrate | Merge after phase gate is green | The integration branch loses local Python/SQLite functionality |
| Reassess | Next slice selected from the gate matrix | The next step depends on an unresolved product decision |

## Phase Gates

### Gate 0: Isolated Commercial Track

Purpose: create a commercial migration lane that cannot disturb the current
mainline.

Must be true:

- Work happens on `codex/commercial-migration-closed-loop` or a child branch.
- Current local `codex/agent-gateway-kb-demo` changes are not modified by this
  lane.
- The lane has this document and the readiness checker.
- Verification passes:

```bash
python3 scripts/commercial_migration_readiness.py
git diff --check
```

### Gate 1: Product Packaging and Entitlement

Purpose: make the product shape sellable without changing core runtime behavior.

Must be true:

- `Free Local`, `Pro Workspace`, `Team Governance`, and `Enterprise/BYOC`
  entitlements are mapped to capabilities, limits, and enforcement points.
- The app can report its current edition and disabled capabilities without
  contacting a billing provider.
- Local development stays fully usable without external auth or billing.
- Verification includes entitlement unit/smoke coverage and token-omission
  checks.

### Gate 2: Production Safety Baseline

Purpose: make shared or customer deployment fail closed.

Must be true:

- `agentops security production-readiness` clearly distinguishes local demo mode
  from production/shared deployment.
- Admin/API auth, scoped agent sessions, workspace isolation, approval policy,
  and audit evidence have smoke coverage.
- The Next.js governance parity page renders production readiness,
  workspace/RBAC entitlement state, short-lived session governance, and audit
  evidence through read-only MIS proxy loaders without exposing raw session IDs.
- Live Hermes/OpenClaw execution still requires readiness and explicit
  confirmation.
- Production mode disables local-dev Agent Gateway fallback: without
  `AGENTOPS_API_KEY` or scoped agent token/session, Agent Gateway read/write
  routes return `401`; without `AGENTOPS_ADMIN_KEY`, enrollment/session admin
  routes return `401`.
- `security_production_readiness_smoke.py --configured-production-fixture`
  starts an isolated production-mode server with temporary API/admin keys,
  proves no-auth readiness remains blocked, authenticated API and CLI readiness
  become ready with `auth_mode=global_api_key`, admin-key enrollment list is
  allowed, the SQLite ledger is not mutated, and the configured keys are omitted
  from output.
- `production_auth_fail_closed_smoke.py --configured-production-fixture` starts
  an isolated production-mode server without API/admin keys and proves
  enrollment, session, task-pull, and task-create Agent Gateway routes return
  `401` without mutating the SQLite ledger.
- The scope/workspace governance smokes use `--isolated-fixture` so they start
  a temporary local server and SQLite ledger instead of depending on whatever
  happens to be running on `127.0.0.1:8787`; Agent Gateway run-start checks
  submit and verify a minimal Agent Plan before starting runs.
- Verification includes:

```bash
python3 scripts/production_auth_fail_closed_smoke.py --configured-production-fixture
python3 scripts/security_production_readiness_smoke.py --configured-production-fixture
python3 scripts/agent_gateway_scope_matrix_smoke.py --isolated-fixture
python3 scripts/workspace_isolation_smoke.py --isolated-fixture
python3 scripts/workspace_rbac_governance_smoke.py --isolated-fixture
python3 scripts/workspace_memory_session_governance_smoke.py --isolated-fixture
python3 scripts/enrollment_approval_workflow_smoke.py
```

### Gate 3: Storage Boundary Before Postgres

Purpose: prepare Postgres without forking product logic.

Must be true:

- SQLite access is isolated behind repository/helper functions for the flows
  being migrated.
- Initial workspace-scoped task/run/memory reads are mapped in
  `docs/STORAGE_BOUNDARY_MAP.md`.
- Schema changes have repeatable migrations and isolated smoke tests using
  `AGENTOPS_DB_PATH`.
- Postgres is introduced as an adapter target after SQLite behavior is locked by
  tests.
- Shared fixture parity compares SQLite and Postgres outcomes before any
  storage adapter is treated as BYOC-ready.
- Route read-model parity compares selected current API response shapes before
  a Postgres-backed server route can replace SQLite reads.
- Backend selection is explicit and fail-closed: Postgres cannot silently fall
  back to SQLite when BYOC prerequisites are missing.
- A Postgres-backed server can start only in explicit read-only HTTP mode at
  this gate: selected GET routes must match the locked read-model hash, while
  POST/PATCH writes fail closed until the write adapter is proven.
- The Postgres-backed read-only server must preserve the machine-facing
  Agent Gateway CLI/API read contract for selected `agentops` commands, not
  only browser/human API reads; this includes Agent Plan and plan-evidence
  list/get/verify readback before Postgres writes are enabled.
- Postgres write helpers must match SQLite outcomes and snapshots before any
  routed HTTP/CLI write surface is enabled.
- The first routed Postgres HTTP writes are explicit task, execution-start,
  agent/run progress and completion heartbeat, execution-evidence, plan-evidence, memory-candidate,
  approval-request, run/task-bound audit, and fixed Hermes/OpenClaw
  prepared-action exact-resume allowlist routes behind
  `AGENTOPS_POSTGRES_WRITE_HTTP=1`:
  `POST /api/tasks`, scoped `POST /api/agent-gateway/tasks`, scoped
  `POST /api/agent-gateway/tasks/:task_id/claim`, scoped
  `POST /api/agent-gateway/runs/start`, scoped
  `POST /api/agent-gateway/heartbeat`, scoped
  `POST /api/agent-gateway/runs/:run_id/heartbeat`, scoped
  `POST /api/agent-gateway/tool-calls`, scoped
  `POST /api/agent-gateway/artifacts`, scoped
  `POST /api/agent-gateway/evaluations/submit`, scoped
  `POST /api/agent-gateway/agent-plans`, scoped
  `POST /api/agent-gateway/plan-evidence-manifests`, scoped
  `POST /api/agent-gateway/memories/propose`, scoped
  `POST /api/agent-gateway/approvals/request`, scoped
  `POST /api/agent-gateway/audit`, fixed
  `POST /api/integrations/openclaw/probe`, fixed
  `POST /api/integrations/hermes/run-task`, and row-gated
  `POST /api/approvals/:approval_id/approve` for those two fixed runtime
  prepared actions; read-only mode must still block all of them,
  the allowlisted writes must persist task/run/progress-heartbeat/completion-heartbeat/tool/evaluation/artifact/Agent
  Plan/plan-evidence/memory/approval/audit/runtime/prepared-action evidence in
  Postgres, scoped Gateway writes must reject absent tokens, missing scopes,
  body/header cross-workspace, cross-agent, same-workspace intruder attempts,
  run heartbeat task mismatches, terminal run revival, memory overwrite attempts,
  manifest binding mismatches, approval task/tool/requester mismatches,
  approved approval overwrite attempts, and audit entity/run/task mismatches,
  fixed runtime routes must reject premature resume/hash mismatch/replay while
  consuming exactly once after approval, non-prepared approval decisions must
  remain blocked, and broader mutation routes such as memory review decisions,
  knowledge index, non-fixed live-runtime heartbeat/daemon control, and admin mutations must
  remain blocked until each has a dedicated smoke.
- The first Postgres-backed Agent Gateway CLI/API writes must use the actual
  `agentops` CLI against the same allowlist, not direct HTTP fixtures only:
  read-only CLI writes, missing-scope CLI writes, and non-allowlisted CLI
  mutation commands must fail closed, while scoped CLI commands persist task,
  run, heartbeat, tool/evaluation/artifact, Agent Plan, verified
  plan-evidence, memory, approval, audit, and completion heartbeat evidence in
  Postgres with no token leakage or SQLite fallback.
- Verification includes local acceptance against a temporary SQLite database
  before any Postgres work starts:

```bash
python3 scripts/storage_boundary_sqlite_smoke.py
python3 scripts/storage_postgres_boundary_parity_smoke.py
python3 scripts/storage_postgres_route_read_model_smoke.py
python3 scripts/storage_backend_selection_smoke.py
python3 scripts/storage_postgres_http_read_parity_smoke.py
python3 scripts/storage_postgres_cli_read_parity_smoke.py
python3 scripts/storage_postgres_write_helper_parity_smoke.py
python3 scripts/storage_postgres_http_write_task_smoke.py
python3 scripts/storage_postgres_cli_write_parity_smoke.py
```

### Gate 4: UI/API Parity Before Next.js

Purpose: prevent a frontend rewrite from becoming a product regression.

Must be true:

- Current Vite/React routes and API calls have a page-by-page parity checklist.
  The canonical checklist is `docs/UI_API_PARITY_MATRIX.md`, backed by
  `docs/UI_API_PARITY_MATRIX.json` (`ui_api_parity_matrix_v1`) and verified by
  `python3 scripts/ui_api_parity_matrix_smoke.py`.
- Next.js work starts in a separate app or worktree and consumes the same API
  semantics first.
- No route is retired until customer dispatch, worker console, reports,
  approvals, memory, and audit paths are verified in both UIs or explicitly
  deferred.
- The Next.js deployment route must load `/api/storage/backend-status` through
  the MIS proxy/server loader and surface SQLite default state, Postgres/BYOC
  prerequisites, read-only mode, write blocking, fallback status, contract ID,
  and next proof before any storage-backed route replacement is considered.
- Verification includes current Vite build plus browser snapshots and critical
  review interactions before a Next.js route is accepted. The canonical Vite
  browser snapshot smoke must keep proving the current product UI while the
  Next.js track advances in parallel.
- Real Hermes/OpenClaw product-readiness claims must also keep
  `python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes
  --require-hermes-api` green against a local MIS API with the runtimes
  available. That acceptance path must create and verify an Agent Plan before
  Agent Gateway run start, bind the run to a verified plan-evidence manifest,
  create unique task/run/prepared-action IDs for each probe, and drive
  prepared-action exact resume until the live action is consumed.
- Browser verification is automated by:

```bash
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/ui_task_run_route_parity_smoke.py
python3 scripts/ui_route_naming_decision_smoke.py
python3 scripts/ui_legacy_route_alias_smoke.py
python3 scripts/ui_navigation_inventory_smoke.py
python3 scripts/ui_route_retirement_packet_smoke.py
python3 scripts/ui_covered_route_retirement_packet_smoke.py
python3 scripts/pixel_office_dispatch_retirement_evidence_smoke.py
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

  The matrix smoke statically compares actual Vite routes, actual Next App
  Router pages/routes, API contracts, evidence commands, and retirement gates so
  page parity cannot drift into undocumented route replacement.

  `python3 scripts/pixel_office_dispatch_retirement_evidence_smoke.py`
  (`pixel_office_dispatch_retirement_evidence_v1`) records Pixel Office /
  Dispatch as visually evidenced for Next migration without retiring Vite. It
  verifies `/workspace/pixel-office` still exists in Vite, Next owns the Pixel
  Office and Dispatch route fallbacks, Vite/Next browser evidence names both
  sides, omission rules stay fail-closed, and a future route change still needs
  an explicit retirement commit.

  `python3 scripts/nextjs_pixel_office_floor_smoke.py`
  (`nextjs_pixel_office_floor_v1`) starts isolated MIS API and Next.js servers,
  proves `/workspace/pixel-office` renders a read-only Pixel Operating Map from
  dashboard/agent/task/run/approval/memory/audit read models, exposes
  commercial-safe geometry/no-Star-Office/live-runtime-disabled proof, links
  zones into formal Next ledgers, exposes the owner dispatch workflow route
  bridge to Dispatch/Approvals/Reports/Runs, and leaks no token-like material.

  `python3 scripts/nextjs_pixel_office_dispatch_smoke.py`
  (`nextjs_pixel_office_dispatch_v1`) starts isolated Pro MIS API and Next.js
  servers, proves Pixel Office exposes the owner dispatch workflow bridge, then
  exercises the Next Dispatch owner task dry-run and template async job form
  fallbacks with team/risk/priority forwarding, task/job readback through the
  Next proxy, and token/raw-prompt omission.

  `python3 scripts/nextjs_control_tower_parity_smoke.py`
  (`nextjs_control_tower_parity_v1`) starts isolated MIS API and Next.js
  servers, verifies the split Control Tower surface across `/workspace`,
  `/workspace/agents`, `/workspace/governance`, and `/workspace/deployment`,
  compares direct and proxied `/dashboard/metrics`, reads `GET /agents`,
  production-readiness, local-readiness, and storage-backend evidence through
  Next, and checks the transcript for token-like leakage.

  `python3 scripts/nextjs_template_switching_smoke.py`
  (`nextjs_template_switching_parity_v1`) starts isolated MIS API and Next.js
  servers, proves `/workspace/templates` renders live `/template-packages`,
  `/template-bindings`, `/bases`, and `/migration/preview` evidence, exercises
  the migration-preview form fallback, and keeps the transcript free of
  token-like material. This covers the former full template/base-switching gap
  while keeping Vite `/admin/templates` retirement blocked until an explicit
  route retirement commit.

  `python3 scripts/nextjs_local_brief_smoke.py` (`nextjs_local_brief_v1`)
  starts isolated MIS API and Next.js servers, proves the Next
  `/api/mis/workflows/local-brief` proxy and
  `/workspace/pixel-office/local-brief` fallback expose dry-run local brief
  controls plus prepared-action live controls: prepare creates approval-bound
  evidence without calling Agnesfallback, premature resume returns
  `approval_required`, hash mismatch and replay are blocked, and approved exact
  resume consumes the action after one provider call while avoiding prompt body,
  token, or raw response leakage.

  `python3 scripts/local_brief_prepared_action_smoke.py`
  (`local_brief_prepared_action_v1`) locks the backend local-brief approval
  wall: a safe structured state snapshot is stored under `AGENTOPS_RUNTIME_DIR`,
  approval alone performs no provider call, exact resume writes run/artifact
  evidence, and replay stays fail-closed.

  `python3 scripts/nextjs_customer_worker_dispatch_smoke.py`
  (`nextjs_customer_worker_dispatch_v1`) starts isolated MIS API and Next.js
  servers, proves Next `/api/mis/workflows/customer-worker-task` plus
  `/workspace/dispatch/customer-worker` can run one safe mock customer-worker
  dispatch, read task/run/delivery approval/verified plan-evidence back through
  the Next proxy, and fail closed for invalid adapters with `adapter_invalid`.

  `python3 scripts/nextjs_customer_worker_async_job_smoke.py`
  (`nextjs_customer_worker_async_job_v1`) starts isolated MIS API and Next.js
  servers, proves Next `/api/mis/workflows/customer-worker-task/submit` plus
  `/workspace/dispatch/customer-worker-job` can submit one safe mock async
  customer-worker job, read workflow job/task/run/verified plan-evidence back
  through the Next proxy, render the async job list, and fail closed before job
  creation for invalid adapters with `adapter_invalid`.

  `python3 scripts/nextjs_customer_worker_prepared_action_smoke.py`
  (`nextjs_customer_worker_prepared_action_v1`) starts a monkeypatched isolated
  MIS API provider plus Next.js, proves Hermes/OpenClaw customer-worker sync
  and async requests enter the backend prepared-action wall through the Next
  proxy and form fallback, require approval before resume, block request-hash
  mismatch and replay, and read back
  `/api/mis/workflows/customer-worker-prepared-actions` so the Dispatch page
  can render ledger-derived pending/approved actions with safe redacted
  `resume_form` fields. The readback still surfaces only IDs, adapter,
  sync/async flag, approval decision, request hashes, status/result ids, and
  omission flags.

  The task/run route parity smoke starts isolated MIS API and Next.js servers,
  verifies Next task/run list links to detail routes, compares direct MIS API
  task/run list/detail/graph read models with the Next `/api/mis/*` proxy, and
  checks for token-like leakage.

  The Next enrollment request smoke starts isolated MIS API and Next.js
  servers, proves the commercial App Router worker console can request remote
  Agent Gateway enrollment through the approval path, proves the Team
  Governance `approval_policies` entitlement gate is visible on
  `/workspace/governance`, rejects invalid scopes at the Next guard, and keeps
  raw token mint routes blocked with
  `enrollment_token_issue_not_allowed_next_parity`. Direct token issue,
  rotation, and revocation remain outside the Next browser migration slice.

  The route naming decision smoke verifies the structured
  `ui_route_naming_decision_v1` contract: Next `/workspace` task/run routes are
  the future commercial namespace, Vite `/admin` task/run routes remain legacy
  compatibility routes, and every task/run retirement still requires a
  backward-compatible redirect or alias plus an explicit route retirement
  commit.

  The legacy route alias smoke starts a Next.js dev server and verifies Next
  `/admin/tasks/:taskId`, `/admin/runs`, and `/admin/runs/:runId` deep links
  redirect to their `/workspace` task/run targets without allowing Vite route
  retirement.

  The navigation inventory smoke verifies `ui_navigation_inventory_v1`: Next
  primary task/run navigation uses `/workspace`, Next `/admin` task/run routes
  are redirect aliases only, and the route naming decision now has canonical
  navigation evidence while still blocking route retirement until an explicit
  retirement commit.

  The route retirement packet smoke verifies `ui_route_retirement_packet_v1`:
  the task/run `/admin` routes have a candidate-only retirement packet with
  exact commit evidence requirements, but `retirement_action` remains
  `not_executed` and `retirement_allowed` remains false until a route-pair
  retirement commit lands.

  The covered-route retirement packet smoke verifies
  `ui_covered_route_retirement_packet_v1`: Control Tower and Worker Console are
  covered Next candidates, but Vite `/admin` and `/workspace/agents` remain
  live. The packet is candidate-only, requires future deep-link compatibility
  plus rerun Vite/Next browser evidence, and keeps Agent Gateway CLI/API/MCP
  unchanged before any explicit route retirement commit.

  The Vite smoke starts isolated MIS API and Vite dev servers, captures
  canonical Vite route snapshots for workspace, Pixel Office, tasks, agents,
  approvals, memory, reports, run ledger, Vite `/admin/tasks/:id` task detail,
  Vite `/admin/runs/:id` run detail, audit, and customer project report,
  verifies `/mis-api/*` proxy reads, and checks for token-like leakage. These
  detail snapshots are evidence for the existing Vite routes; they are not a
  retirement or rename decision.

  The Next.js smoke starts isolated MIS API and Next.js servers, captures route
  snapshots, approves one pending approval through the Next.js approvals page,
  approves one candidate memory through the Next.js memory page, verifies both
  state changes through `/api/mis/*`, renders a fixture-backed customer project
  report, opens the commercial entitlement, governance, deployment, and tool
  call ledger, evaluation room, runtime connector, Notion external-base, and
  agent detail parity pages, updates one runtime connector trust policy through
  the Next.js form fallback, verifies Notion dry-run export and Free Local
  confirmed-export entitlement blocking, archives that report to the MIS ledger
  through a Next.js form fallback,
  verifies `report_artifact_id`, clicks a customer template dispatch action,
  verifies the Free Local `report_templates` entitlement block, confirms no
  customer project was created by the blocked action, flips an isolated temporary
  entitlement fixture to `pro_workspace`, clicks the same Next.js dispatch path
  again, verifies the six-task KB bot customer project, six run ledger rows,
  `report_artifact_id`, six Agent Plans, and five
  `verified_plan_evidence_manifests` are created, opens the created project
  report page, verifies visible Agent Plan / plan-evidence status, opens a
  manifest evidence drilldown page, verifies read-only verification/run-graph
  evidence, opens linked task and run detail pages, and checks for token-like
  leakage. This is isolated mock/offline fixture evidence for the Next.js
  commercial template path; it is not live Hermes/OpenClaw runtime proof or
  full BYOC production readiness evidence.

  The Next Agent Gateway task proxy smoke starts isolated MIS API and Next.js
  servers with local no-token fallback disabled, then proves
  `POST /api/mis/agent-gateway/tasks` preserves the scoped Gateway contract:
  no token is `401`, missing `tasks:create`, workspace, and agent impersonation
  are `403`, valid scoped tokens create and read back the task through the Next
  proxy, and direct MIS readback matches without token leakage.

  The Next Agent Gateway CLI worker dogfood smoke starts isolated MIS API and
  Next.js servers, creates a scoped task through the Next
  `/api/mis/agent-gateway/tasks` proxy, runs the repo worker CLI entrypoint once
  with the scoped token, and reads the completed task, run/tool/evaluation
  evidence, and verified plan-evidence manifest back through the Next proxy.
  This binds the Next migration track to the real agent-facing CLI/API
  execution contract while keeping live Hermes/OpenClaw execution behind the
  explicit confirm-run gate.

  The Next worker dispatch smoke starts isolated MIS API and Next.js servers,
  sets `AGENTOPS_BASE_URL` so the worker subprocess writes into that isolated
  ledger, then proves the Next `/api/mis/workers/local/dispatch-once` proxy and
  `/workspace/agents/dispatch-once` form fallback can run one safe `mock`
  worker, persist task/run/verified plan-evidence proof, read the completed
  task back without token leakage, and reject non-mock proxy/form dispatch
  before upstream execution with `mock_only_next_parity`. This does not retire
  Vite worker controls or enable live Hermes/OpenClaw dispatch in Next.

  The Next worker stuck-release smoke starts isolated MIS API and Next.js
  servers, creates stale running worker tasks, proves the Next
  `/api/mis/workers/stuck-tasks` read path plus
  `/api/mis/workers/tasks/release` mutation can return one task to `planned`
  and block the linked running run as `WorkerTaskReleased`, proves the
  `/workspace/agents/release-task` form fallback performs the same recovery,
  and proves `force:true` is rejected at the Next proxy with
  `force_release_not_allowed_next_parity`.

  The Next worker gateway lifecycle guard smoke starts isolated MIS API and
  Next.js servers, creates a real backend enrollment/session as setup proof that
  backend CLI/API paths can issue one-time credentials, then proves the Next
  `/api/mis` proxy blocks Agent Gateway session create, session revoke, and
  enrollment revoke writes with `gateway_lifecycle_write_not_allowed_next_parity`.
  `/workspace/agents` only renders session hygiene readback with token/session
  omission proof, while backend CLI/API lifecycle controls remain canonical.

  `python3 scripts/nextjs_worker_console_parity_smoke.py`
  (`nextjs_worker_console_parity_v1`) proves the split Worker Console coverage:
  `/workspace/agents` handles registry, production security, safe mock worker
  dispatch, mock daemon controls, stuck-task release, approval-gated enrollment,
  and session hygiene, while `/workspace/workers` renders fleet/readiness,
  hygiene preview, local readiness, operator execution-mode, and a visible
  Worker Console coverage boundary. Agent Gateway CLI/API/MCP remains canonical
  for token issue/rotate/revoke, session lifecycle, live daemon lifecycle, live
  dispatch controls, cleanup mutation, and detailed operator mutation.

  The Next worker daemon control smoke starts isolated MIS API and Next.js
  servers with a temporary runtime directory, proves the Next
  `/api/mis/workers/local/start|restart|stop` proxy and
  `/workspace/agents/daemon-control` form fallback can control only the safe
  `mock` daemon, and proves non-mock/live daemon controls fail closed before
  upstream execution.

- First migration artifact:
  - `agentops_mis_cli/worker.py`
  - `ui/next-app/app/workspace/page.tsx`
  - `ui/next-app/app/workspace/agents/page.tsx`
  - `ui/next-app/app/workspace/agents/[agentId]/page.tsx`
  - `ui/next-app/app/workspace/agents/dispatch-once/route.ts`
  - `ui/next-app/app/workspace/agents/release-task/route.ts`
  - `ui/next-app/app/workspace/agents/daemon-control/route.ts`
  - `ui/next-app/app/workspace/commercial/page.tsx`
  - `ui/next-app/app/workspace/governance/page.tsx`
  - `ui/next-app/app/workspace/deployment/page.tsx`
  - `ui/next-app/app/workspace/pixel-office/page.tsx`
  - `ui/next-app/app/workspace/pixel-office/local-brief/route.ts`
  - `ui/next-app/app/workspace/dispatch/page.tsx`
  - `ui/next-app/app/workspace/dispatch/template-run/route.ts`
  - `ui/next-app/app/workspace/templates/page.tsx`
  - `ui/next-app/app/workspace/templates/migration-preview/route.ts`
  - `ui/next-app/app/workspace/evidence/[manifestId]/page.tsx`
  - `ui/next-app/app/workspace/tasks/page.tsx`
  - `ui/next-app/app/workspace/tasks/[taskId]/page.tsx`
  - `ui/next-app/app/workspace/runs/page.tsx`
  - `ui/next-app/app/workspace/runs/[runId]/page.tsx`
  - `ui/next-app/app/workspace/tool-calls/page.tsx`
  - `ui/next-app/app/workspace/evaluations/page.tsx`
  - `ui/next-app/app/workspace/connectors/page.tsx`
  - `ui/next-app/app/workspace/connectors/trust/route.ts`
  - `ui/next-app/app/workspace/external-bases/notion/page.tsx`
  - `ui/next-app/app/workspace/external-bases/notion/export/route.ts`
  - `ui/next-app/app/workspace/agents/enrollment-request/route.ts`
  - `ui/next-app/app/admin/tasks/[taskId]/page.tsx`
  - `ui/next-app/app/admin/runs/page.tsx`
  - `ui/next-app/app/admin/runs/[runId]/page.tsx`
  - `ui/next-app/app/workspace/approvals/page.tsx`
  - `ui/next-app/app/workspace/approvals/review/route.ts`
  - `ui/next-app/app/workspace/memory/page.tsx`
  - `ui/next-app/app/workspace/memory/review/route.ts`
  - `ui/next-app/app/workspace/reports/page.tsx`
  - `ui/next-app/app/workspace/customer-projects/[projectId]/report/page.tsx`
  - `ui/next-app/app/workspace/customer-projects/[projectId]/report/archive/route.ts`
  - `ui/next-app/app/workspace/dispatch/customer-worker/route.ts`
  - `ui/next-app/app/workspace/dispatch/customer-worker-job/route.ts`
  - `ui/next-app/app/workspace/audit/page.tsx`
  - `ui/next-app/app/api/mis/[...path]/route.ts`
  - `ui/next-app/src/lib/mis.ts`
  - `ui/next-app/src/lib/misServer.ts`
  - `ui/next-app/src/components/AgentDetailPage.tsx`
  - `ui/next-app/src/components/LedgerPages.tsx`
  - `ui/next-app/src/components/LedgerDetailPages.tsx`
  - `ui/next-app/src/components/ToolCallPages.tsx`
  - `ui/next-app/src/components/EvaluationPages.tsx`
  - `ui/next-app/src/components/ConnectorPages.tsx`
  - `ui/next-app/src/components/NotionBasePage.tsx`
  - `ui/next-app/src/components/CommercialPage.tsx`
  - `ui/next-app/src/components/GovernancePage.tsx`
  - `ui/next-app/src/components/DeploymentPage.tsx`
  - `ui/next-app/src/components/WorkspaceDashboard.tsx`
  - `ui/next-app/src/components/PixelOfficePage.tsx`
  - `ui/next-app/src/components/DispatchPage.tsx`
  - `ui/next-app/src/components/TemplateSwitchingPage.tsx`
  - `ui/next-app/src/components/DeliveryPages.tsx`
  - `ui/next-app/src/styles/globals.css`
  - `scripts/nextjs_parity_smoke.py`
  - `scripts/nextjs_agent_gateway_task_proxy_smoke.py`
  - `scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py`
  - `scripts/nextjs_worker_dispatch_once_smoke.py`
  - `scripts/nextjs_pixel_office_floor_smoke.py`
  - `scripts/nextjs_control_tower_parity_smoke.py`
  - `scripts/nextjs_template_switching_smoke.py`
  - `scripts/local_brief_prepared_action_smoke.py`
  - `scripts/nextjs_local_brief_smoke.py`
  - `scripts/nextjs_customer_worker_dispatch_smoke.py`
  - `scripts/nextjs_customer_worker_async_job_smoke.py`
  - `scripts/nextjs_customer_worker_prepared_action_smoke.py`
  - `scripts/nextjs_worker_stuck_release_smoke.py`
  - `scripts/nextjs_worker_daemon_control_smoke.py`
  - `scripts/nextjs_enrollment_request_smoke.py`
  - `scripts/nextjs_worker_gateway_lifecycle_guard_smoke.py`
  - `scripts/nextjs_worker_console_parity_smoke.py`
  - `scripts/operator_execution_mode_smoke.py`
  - `scripts/nextjs_playwright_snapshot_smoke.py`
  - `scripts/vite_playwright_snapshot_smoke.py`
  - `docs/UI_API_PARITY_MATRIX.md`
  - `docs/UI_API_PARITY_MATRIX.json`
  - `docs/UI_ROUTE_NAMING_DECISION.md`
  - `docs/UI_ROUTE_NAMING_DECISION.json`
  - `docs/UI_NAVIGATION_INVENTORY.md`
  - `docs/UI_NAVIGATION_INVENTORY.json`
  - `docs/UI_ROUTE_RETIREMENT_PACKET.md`
  - `docs/UI_ROUTE_RETIREMENT_PACKET.json`
  - `docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.md`
  - `docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json`
  - `scripts/ui_api_parity_matrix_smoke.py`
  - `scripts/ui_task_run_route_parity_smoke.py`
  - `scripts/ui_route_naming_decision_smoke.py`
  - `scripts/ui_legacy_route_alias_smoke.py`
  - `scripts/ui_navigation_inventory_smoke.py`
  - `scripts/ui_route_retirement_packet_smoke.py`
  - `scripts/ui_covered_route_retirement_packet_smoke.py`

### Gate 5: BYOC / Enterprise Deployment

Purpose: make customer-owned deployment operationally credible.

Must be true:

- Deployment mode, backup/restore, retention, signed export, SSO/RBAC hooks, and
  private connector policy are documented and smoke-tested where local
  simulation is possible.
- `release_evidence_packet_v1` and `commercial_release_evidence_packet_v1`
  make the release/handoff gate machine-checkable: the packet must require the
  backend Postgres readiness fixture, the Next.js Postgres browser fixture, the
  BYOC Postgres handoff fixture, and real Hermes/OpenClaw local runtime
  acceptance before a commercial handoff can claim readiness. Verify with
  `python3 scripts/release_evidence_packet_smoke.py` and
  `python3 scripts/commercial_release_evidence_packet_smoke.py`.
- `commercial_handoff_status_v1` is the CI-safe operator status aggregate for
  release, commercial, freeze, and merge packets. It reports
  `phase_gate_statuses`, `explicit_blockers`, and `required_commands` through
  `python3 scripts/commercial_handoff_status.py`; verify the surface with
  `python3 scripts/commercial_handoff_status_smoke.py`.
- `commercial_evidence_receipts_v1` is the local hash/ref-only receipt ledger
  for verified commands. Gates 1-5 can have local receipts while still not being
  release-grade until exact-head CI, remote sync, clean worktree, and all phase
  gates are current. Verify it with
  `python3 scripts/commercial_evidence_receipts_smoke.py`.
- `commercial_current_evidence_status_v1` is the evidence coverage layer under
  the handoff aggregate. It reports per-gate `evidence_current`,
  `local_receipt_current`, `gates_requiring_current_evidence`, heavy/live
  evidence classes, and forbidden evidence without executing Docker, browser,
  Postgres, or live runtime checks.
  Verify with `python3 scripts/commercial_current_evidence_status_smoke.py`.
- `commercial_release_promotion_preflight_v1` is the CI-safe promotion preflight
  between local receipts and release-grade evidence. It reads git/docs state and
  blocks promotion until local receipts, release-grade receipts, clean worktree,
  remote sync, exact-head CI, handoff, and merge readiness are all current.
  Verify with `python3 scripts/commercial_release_promotion_preflight_smoke.py`;
  strict promotion first reads external GitHub Actions state with
  `python3 scripts/commercial_exact_head_ci_evidence.py --from-gh --require-current-head`,
  then uses
  `python3 scripts/commercial_release_promotion_preflight.py --include-external-ci-evidence --require-promotion-ready`.
- `release_freeze_protocol_v1` keeps commercial handoff in
  `freeze_active_not_release_complete`, and `merge_readiness_status_v1` keeps
  merge status at `blocked_release_evidence_required` until release evidence,
  Gate 5 BYOC/Postgres fixtures, real Hermes/OpenClaw acceptance, clean
  worktree, remote sync, and exact-head CI evidence are current. Verify with
  `python3 scripts/release_freeze_protocol_smoke.py` and
  `python3 scripts/merge_readiness_status_smoke.py`.
- The Next.js deployment parity page renders local readiness, backup/restore
  evidence, retention/export gates, SSO hooks, and private connector policy
  through read-only MIS proxy loaders; restore remains CLI-confirmed and is not
  exposed as a browser write.
- The same deployment route consumes `storage.runtime_write_gate` from
  `/api/storage/backend-status` so the commercial UI shows the fixed Postgres
  Hermes/OpenClaw prepared-action write contracts, the row-gated approval
  decision route, exact-resume proof, and non-fixed runtime fail-closed state
  instead of leaving that evidence buried in backend smoke output.
- `nextjs_deployment_postgres_runtime_write_fixture_v1` starts a temporary
  Postgres-backed MIS API in explicit `experimental_write_http` mode and a
  Next.js server pointed at it, then verifies `/workspace/deployment` renders
  `runtime_write_gate=active`, the two fixed runtime write contracts, OpenClaw
  probe, Hermes run-task, row-gated approval approve, exact-resume proof, and
  non-fixed runtime writes blocked at the proxy. Verify with
  `python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture`.
- `deployment_readiness_postgres_runtime_write_fixture_v1` proves the same
  fixed-runtime Postgres write gate through backend API and CLI, not only the
  browser: it starts a temporary Postgres `experimental_write_http` MIS server,
  verifies `GET /api/deployment/readiness` and `agentops deployment readiness`
  expose `storage.runtime_write_gate=active`, checks the three fixed runtime
  routes, keeps non-allowlisted writes blocked at `503`, and confirms readiness
  reads do not mutate Postgres ledger counts. Verify with
  `python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture`.
- `byoc_deployment_acceptance_v1` runs a local isolated recovery and audit
  export drill: backup create/verify/restore, restore confirmation guard,
  overwrite safety copy, signed audit export with a customer key, raw metadata
  omission, and tamper detection. Its `--postgres-readiness-fixture` handoff
  mode also invokes the backend Postgres deployment readiness fixture and
  requires `runtime_write_gate=active`, `experimental_write_http`, the
  fixed OpenClaw/Hermes/row-gated approval routes, `postgres_read_only_backend`
  blocking for non-allowlisted writes, and unchanged Postgres ledger counts.
  Verify with
  `python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture`.
- `enterprise_byoc_controls_v1` exposes a read-only, metadata-only Enterprise
  controls proof through `GET /api/deployment/enterprise-controls` and
  `agentops deployment enterprise-controls`. It summarizes configured SSO
  metadata and private connector registry/trust policy without exposing client
  secrets, certificates, raw connector config, tokens, or executing live
  connector work.
- `deployment_readiness_v1` exposes the Gate 5 deployment verdict through
  `GET /api/deployment/readiness`, `agentops deployment readiness`, and the
  Next.js `/workspace/deployment` page. It aggregates local readiness,
  production security, storage backend, backup/restore, signed audit export,
  retention, SSO/private connector gates, and omission contracts without
  executing live work, restoring a database, or printing secrets. Verify with
  `python3 scripts/deployment_readiness_smoke.py --configured-retention-fixture --configured-enterprise-fixture`;
  the configured retention mode proves the deployment verdict sees ready
  retention controls from a temporary legal-hold registry, and the configured
  Enterprise mode proves API and CLI readback show `enterprise_byoc_controls_v1`
  and the SSO/private connector policy gate ready under `enterprise_byoc`
  without selecting Postgres, exposing raw enterprise control metadata, or
  mutating the ledger. The Next.js browser parity smoke also flips an
  isolated entitlement fixture to `enterprise_byoc`, loads a temporary
  `AGENTOPS_RETENTION_CONTROLS_PATH` and `AGENTOPS_ENTERPRISE_CONTROLS_PATH`,
  and verifies `/workspace/deployment`
  renders ready retention policy/controls gates, `active holds 1`, cleanup
  closed, ready SSO/private connector policy, `private connectors 1/2`,
  dangerous cleanup queries fail closed, raw legal-hold detail omitted, raw
  enterprise control metadata omitted, and no SQLite ledger mutation. Verify the
  focused browser fixture with
  `python3 scripts/nextjs_playwright_snapshot_smoke.py --configured-retention-fixture`.
- `audit_retention_policy_v1` exposes a read-only audit retention policy
  preview through `GET /api/audit/retention-policy` and
  `agentops audit retention-policy`. It proves policy source, retention-day
  bounds, cutoff calculation, eligible audit-row counts, and raw-row omission
  without deleting rows, mutating the ledger, or claiming production retention
  enforcement. `delete`, `apply`, and cleanup-style query parameters fail
  closed while preserving `rows_deleted=0`. Verify with
  `python3 scripts/audit_retention_policy_smoke.py`.
- `audit_retention_controls_v1` exposes read-only retention control readiness
  through `GET /api/audit/retention-controls` and
  `agentops audit retention-controls`. It proves cleanup approval is required,
  legal-hold checks are required before any future cleanup, cleanup endpoints
  stay closed, legal-hold summaries omit raw subject/reason detail, and
  destructive cleanup remains unsupported. Its configured fixture mode starts an
  isolated `pro_workspace` server with a temporary legal-hold registry and
  proves `active_holds` without leaking raw hold detail; this is readiness
  evidence, not a legal system of record. Verify with
  `python3 scripts/audit_retention_controls_smoke.py --configured-fixture`.
- Postgres adapter and migrations pass the same core ledger acceptance used for
  SQLite.
- Runtime connectors remain policy-gated and do not store raw secrets, raw
  prompts, raw responses, or private transcripts by default.

## Technology Decisions

| Area | Current product line | Commercial migration target | Gate |
| --- | --- | --- | --- |
| Backend/control plane | Python `server.py` + stdlib HTTP | Keep until API parity and production safety pass; split services later only if pressure is real | 2 |
| Agent execution | Agent Gateway CLI/API/MCP | Keep as the durable agent contract | 1 |
| UI | Vite + React + TypeScript plus parallel `ui/next-app` | Next.js App Router replaces pages only after parity gate | 4 |
| Database | SQLite | SQLite Free Local, Postgres Team/Enterprise adapter | 3 |
| ORM | Direct SQLite helpers | Adapter/repository boundary first; Prisma/Drizzle only if Next.js owns backend | 3/4 |
| Auth | Local dev/admin key/scoped agent sessions | Production auth, SSO hooks, workspace RBAC | 2/5 |
| Billing | None | Entitlement config first, billing provider later | 1 |
| Assets | Original Pixel Office plus demo-only Star-Office visualizer boundary | Original commercial-safe Pixel Office asset pack | 1 |

## Branch Strategy

Recommended branches:

- `codex/commercial-migration-closed-loop`: integration lane for the migration
  plan, gates, and readiness checks.
- `codex/commercial-entitlements`: edition config, capability gates, and product
  packaging.
- `codex/commercial-production-safety`: production readiness, auth hardening,
  workspace isolation, and audit policy.
- `codex/storage-boundary-postgres`: SQLite boundary and Postgres migration
  preparation.
- `codex/nextjs-parity-spike`: Next.js parity experiment after current UI/API
  behavior is locked.
- `codex/pixel-office-commercial-assets`: commercial-safe visual asset
  replacement.

Commercial work should merge in this order:

1. Closed-loop docs and readiness.
2. Entitlements and product packaging.
3. Production safety baseline.
4. Storage boundary.
5. Commercial asset replacement.
6. Next.js parity spike.
7. Postgres adapter.
8. BYOC deployment hardening.

## Rollback Rules

- A commercial branch can be abandoned without touching `main` or
  `codex/agent-gateway-kb-demo`.
- If a Next.js route fails parity, keep Vite/React as canonical and record the
  gap.
- If Postgres adapter behavior diverges, keep SQLite canonical and add a failing
  adapter test before retrying.
- If entitlement gates block local demo usage, revert the gate and keep the
  edition logic read-only until the product path is smooth.
- If asset replacement slows core product work, keep the non-commercial visual
  demo behind documentation boundaries and ship commercial-safe unbranded UI
  first.

## First Three Work Packages

### WP1: Entitlement Skeleton

Deliver:

- Edition config file with `free_local`, `pro_workspace`, `team_governance`,
  and `enterprise_byoc`.
- Read-only API and CLI output showing current edition and capability flags.
- Smoke test proving disabled capabilities fail closed without billing secrets.

Initial status:

- Example config: `config/entitlements.example.json`
- API: `GET /api/commercial/entitlements`
- CLI: `agentops commercial entitlements`
- Enforcement status: `notion_confirmed_export`, `report_templates`, and
  `approval_policies` report `fail_closed` because they are enforced at
  explicit product boundaries; capabilities without a product-boundary gate
  remain `read_only_preview`.
- First fail-closed gate: Free Local blocks `confirm_export:true` on
  `POST /api/integrations/notion/export-confirmed` for capability
  `notion_confirmed_export`, while Notion preview/dry-run stays available.
- First template gate: Free Local can list customer templates but blocks
  `POST /api/workflows/customer-task-templates/run` and
  `POST /api/workflows/customer-task-templates/submit` for capability
  `report_templates`.
- The entitlement smoke reads back `commercial.entitlement_blocked` audit logs
  from an isolated SQLite ledger and then flips the same local fixture to
  `pro_workspace` to prove the template run path is allowed without billing
  calls or token exposure.
- First Team Governance gate: Free Local and Pro Workspace block approval-based
  remote Agent Gateway enrollment requests for capability `approval_policies`.
  A `team_governance` fixture proves request -> approve -> issue-approved ->
  heartbeat works, and a downgrade check proves approved pending requests cannot
  issue tokens after the edition drops below Team.
- Next.js parity evidence now covers both sides of that gate: Free Local blocks
  `Start template` without creating a project, while an isolated
  `pro_workspace` entitlement fixture allows the same Next.js form fallback to
  create a ledger-backed six-task KB bot customer project, six run ledger rows,
  a report artifact, six Agent Plans, and five verified plan-evidence manifests.
- The Next.js commercial parity page must render current edition, capability
  matrix, fail-closed gates, billing-call omission, and token-omission proof
  through the MIS proxy without introducing billing writes.
- The entitled template path preserves the Agent Gateway evidence contract:
  `scripts/run_kb_bot_demo.py` creates Agent Plans before starting runs and
  records plan-evidence manifests for the completed low-risk/customer-delivery
  steps while keeping the external-upload step approval-gated.
- The Next.js delivery report must render that contract visibly as Agent Plan
  evidence, not only rely on hidden JSON or backend-only smoke assertions.
- The Next.js evidence drilldown must remain read-only and load through Agent
  Gateway read APIs for plan-evidence manifest verification, Agent Plan
  verification, and run graph readback.
- Task and run detail drilldowns must remain read-only and expose linked
  approvals, evaluations, artifacts, audit/runtime evidence, and token-omission
  proof through the Next.js MIS proxy.
- Smoke:
  `python3 scripts/commercial_entitlements_smoke.py`
  `python3 scripts/team_entitlement_enrollment_smoke.py`

### WP2: Production Safety Contract

Deliver:

- Production readiness output expanded with edition, auth, workspace, retention,
  backup, live-runtime, and audit checks.
- Documentation that states which checks are warnings in local demo mode and
  failures in production mode.
- Smoke tests for local and production-requested modes.

### WP3: Storage Boundary Map

Deliver:

- A table mapping high-churn SQLite access paths to future repository helpers.
- One low-risk helper extraction with identical tests.
- A Postgres migration design note that does not introduce Postgres dependency
  yet.

## Definition of Done

The commercial migration closed loop is considered established when:

- This document is linked from README and the parallel branch plan.
- `python3 scripts/commercial_migration_readiness.py` returns
  `overall_status: "ready"` on the commercial branch.
- The readiness output names the current branch, phase gates, verification
  commands, and blocked artifacts.
- `git diff --check` passes.
- No local DB, runtime log, generated service file, `dist`, `node_modules`,
  `.env`, raw credential, raw prompt, raw model response, or private transcript
  is introduced by the migration lane.
