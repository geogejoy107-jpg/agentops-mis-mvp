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

## First Parity Slice

- App Router route: `/workspace`
- Runtime API proxy: `/api/mis/[...path]`
- Live data contract: dashboard metrics, tasks, runs, approvals
- Canonical predecessor: `ui/start-building-app/src/app/components/pages/WorkspaceHome.tsx`

Do not remove the Vite app until this lane passes route, API, and visual parity
for each commercial workflow.
