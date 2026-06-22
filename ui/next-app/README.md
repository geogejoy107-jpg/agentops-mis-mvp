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
python3 scripts/nextjs_playwright_snapshot_smoke.py
```

The Playwright smoke starts an isolated MIS API provider and Next.js dev server,
captures browser snapshots for the current parity routes, checks proxy data, and
fails on token-like output.

## Parity Slices

- App Router route: `/workspace`
- App Router route: `/workspace/agents`
- App Router route: `/workspace/tasks`
- App Router route: `/workspace/runs`
- App Router route: `/workspace/approvals`
- App Router route: `/workspace/memory`
- App Router route: `/workspace/audit`
- Runtime API proxy: `/api/mis/[...path]`
- Live data contract: dashboard metrics, agents, production readiness, worker readiness, tasks, runs, approvals, memories, audit
- Canonical predecessors:
  - `ui/start-building-app/src/app/components/pages/WorkspaceHome.tsx`
  - `ui/start-building-app/src/app/components/pages/AIEmployees.tsx`
  - `ui/start-building-app/src/app/components/pages/MyTasks.tsx`
  - `ui/start-building-app/src/app/components/pages/RunLedger.tsx`
  - `ui/start-building-app/src/app/components/pages/ApprovalsInbox.tsx`
  - `ui/start-building-app/src/app/components/pages/MemoryLibrary.tsx`
  - `ui/start-building-app/src/app/components/pages/AuditCenter.tsx`

Do not remove the Vite app until this lane passes route, API, and visual parity
for each commercial workflow.
