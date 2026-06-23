# UI v2 Implementation Inventory

Repository: `geogejoy107-jpg/agentops-mis-mvp`
Branch: `design/gemini-ui-v2-implementation`
Frozen baseline: `93efdb8725d66ccdde5c5a4dfc274b9f3fbe23b8`
Design source: Draft PR #8
Scope: Phase 0 foundation, Mission Control, and compact Pixel Office integration.

## Priority boundary

The canonical milestone remains hardening, CI/security/concurrency, v1.5 RC, then merge. This is an isolated Draft/P2 implementation and does not change P0/P1 priority.

## Route and data inventory

- `/workspace`: WorkspaceHome; live dashboard, tasks, approvals, runs and memories; becomes Mission Control.
- `/workspace/pixel-office`: PixelOffice; live MIS state with explicit demo fallback; remains Visualize.
- `/workspace/tasks`: MyTasks; live tasks; becomes Operate / Tasks.
- `/workspace/agents`: AIEmployees; mixed agent, worker, gateway, commander, review and delivery APIs; split later.
- `/workspace/approvals`: ApprovalsInbox; live approvals; becomes Security Approvals.
- `/workspace/memory`: MemoryLibrary; mixed; becomes Knowledge & Memory later.
- `/workspace/reports`: Reports; live/partial live; becomes Deliveries.
- `/workspace/customer-projects/:projectId/report`: live customer report.
- `/admin`: ControlTower; live dashboard; preserved as a legacy alias.
- `/admin/evaluations`: mixed evaluation surface; deferred.
- `/admin/agents/:id`, `/admin/tasks/:id`, `/admin/runs`, `/admin/runs/:id`, `/admin/toolcalls`, `/admin/connectors`, `/admin/bases/notion`, `/admin/templates`, `/admin/audit`: preserved formal routes.

All legacy routes remain available. The new shell and aliases are additive.

## Mission Control inputs

Use existing read-only loaders for dashboard metrics, tasks, approvals, runs, memories, agents, worker status, Commander readback, deliveries and the operator action plan where available. Missing relationships remain explicitly unavailable; no arbitrary production metric is invented.

## Existing mega-page boundary

`AIEmployees.tsx` currently combines Agent Directory, Worker Fleet, runtime/gateway readiness, enrollment/session controls, Commander planning and dispatch, Human Review, Customer Delivery, daemon controls and integration health. Phase 0 keeps it intact and links to it until later parity-safe decomposition.

## Reuse and boundaries

Reuse PreferencesContext, liveApi contracts, formal object routes, existing status/risk behavior, and PixelOperatingMap as the typed scene adapter. Use the current React/Vite/TypeScript/Tailwind/Radix/React Router stack.

No server execution, identity, approval, worker, runtime, audit, redaction or schema behavior changes. Pixel Office stays read-only and links to canonical records. Privileged actions remain on existing guarded routes.

## Verification

Create and verify an Agent Plan, run `npm ci` and `npm run build`, smoke legacy/v2 routes, and capture 1440x900, 1024x768 and 390x844 screenshots. Check both locales, both light/dark modes, keyboard focus, reduced motion, empty states and backend-unavailable behavior.
