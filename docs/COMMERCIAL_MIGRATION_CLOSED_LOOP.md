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
- Verification includes:

```bash
python3 scripts/production_auth_fail_closed_smoke.py
python3 scripts/security_production_readiness_smoke.py
python3 scripts/agent_gateway_scope_matrix_smoke.py
python3 scripts/workspace_isolation_smoke.py
python3 scripts/workspace_rbac_governance_smoke.py
python3 scripts/workspace_memory_session_governance_smoke.py
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
- Browser verification is automated by:

```bash
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/ui_task_run_route_parity_smoke.py
python3 scripts/ui_route_naming_decision_smoke.py
python3 scripts/ui_legacy_route_alias_smoke.py
python3 scripts/ui_navigation_inventory_smoke.py
python3 scripts/ui_route_retirement_packet_smoke.py
python3 scripts/vite_playwright_snapshot_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
```

  The matrix smoke statically compares actual Vite routes, actual Next App
  Router pages/routes, API contracts, evidence commands, and retirement gates so
  page parity cannot drift into undocumented route replacement.

  The task/run route parity smoke starts isolated MIS API and Next.js servers,
  verifies Next task/run list links to detail routes, compares direct MIS API
  task/run list/detail/graph read models with the Next `/api/mis/*` proxy, and
  checks for token-like leakage.

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
  call ledger and evaluation room parity pages, archives that report to the MIS
  ledger through a Next.js form fallback,
  verifies `report_artifact_id`, clicks a customer template dispatch action,
  verifies the Free Local `report_templates` entitlement block, confirms no
  customer project was created by the blocked action, flips an isolated temporary
  entitlement fixture to `pro_workspace`, clicks the same Next.js dispatch path
  again, verifies a customer project and report artifact are created, opens the
  created project report page, verifies visible Agent Plan / plan-evidence
  status, opens a manifest evidence drilldown page, verifies read-only
  verification/run-graph evidence, opens linked task and run detail pages, and
  checks for token-like leakage.

- First migration artifact:
  - `ui/next-app/app/workspace/page.tsx`
  - `ui/next-app/app/workspace/agents/page.tsx`
  - `ui/next-app/app/workspace/commercial/page.tsx`
  - `ui/next-app/app/workspace/governance/page.tsx`
  - `ui/next-app/app/workspace/deployment/page.tsx`
  - `ui/next-app/app/workspace/dispatch/page.tsx`
  - `ui/next-app/app/workspace/dispatch/template-run/route.ts`
  - `ui/next-app/app/workspace/evidence/[manifestId]/page.tsx`
  - `ui/next-app/app/workspace/tasks/page.tsx`
  - `ui/next-app/app/workspace/tasks/[taskId]/page.tsx`
  - `ui/next-app/app/workspace/runs/page.tsx`
  - `ui/next-app/app/workspace/runs/[runId]/page.tsx`
  - `ui/next-app/app/workspace/tool-calls/page.tsx`
  - `ui/next-app/app/workspace/evaluations/page.tsx`
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
  - `ui/next-app/app/workspace/audit/page.tsx`
  - `ui/next-app/app/api/mis/[...path]/route.ts`
  - `ui/next-app/src/lib/mis.ts`
  - `ui/next-app/src/lib/misServer.ts`
  - `ui/next-app/src/components/LedgerPages.tsx`
  - `ui/next-app/src/components/LedgerDetailPages.tsx`
  - `ui/next-app/src/components/ToolCallPages.tsx`
  - `ui/next-app/src/components/EvaluationPages.tsx`
  - `ui/next-app/src/components/CommercialPage.tsx`
  - `ui/next-app/src/components/GovernancePage.tsx`
  - `ui/next-app/src/components/DeploymentPage.tsx`
  - `ui/next-app/src/components/DispatchPage.tsx`
  - `ui/next-app/src/components/DeliveryPages.tsx`
  - `ui/next-app/src/styles/globals.css`
  - `scripts/nextjs_parity_smoke.py`
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
  - `scripts/ui_api_parity_matrix_smoke.py`
  - `scripts/ui_task_run_route_parity_smoke.py`
  - `scripts/ui_route_naming_decision_smoke.py`
  - `scripts/ui_legacy_route_alias_smoke.py`
  - `scripts/ui_navigation_inventory_smoke.py`
  - `scripts/ui_route_retirement_packet_smoke.py`

### Gate 5: BYOC / Enterprise Deployment

Purpose: make customer-owned deployment operationally credible.

Must be true:

- Deployment mode, backup/restore, retention, signed export, SSO/RBAC hooks, and
  private connector policy are documented and smoke-tested where local
  simulation is possible.
- The Next.js deployment parity page renders local readiness, backup/restore
  evidence, retention/export gates, SSO hooks, and private connector policy
  through read-only MIS proxy loaders; restore remains CLI-confirmed and is not
  exposed as a browser write.
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
- First fail-closed gate: Free Local blocks `confirm_export:true` on
  `POST /api/integrations/notion/export-confirmed` for capability
  `notion_confirmed_export`, while Notion preview/dry-run stays available.
- First template gate: Free Local can list customer templates but blocks
  `POST /api/workflows/customer-task-templates/run` and
  `POST /api/workflows/customer-task-templates/submit` for capability
  `report_templates`.
- Next.js parity evidence now covers both sides of that gate: Free Local blocks
  `Start template` without creating a project, while an isolated
  `pro_workspace` entitlement fixture allows the same Next.js form fallback to
  create a ledger-backed customer project and report artifact.
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
- Smoke: `python3 scripts/commercial_entitlements_smoke.py`

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
