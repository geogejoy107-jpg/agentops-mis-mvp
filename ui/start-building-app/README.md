# Start Building App

This is a code bundle for Start Building App. The original project is available at https://www.figma.com/design/jVwiVjVKZJlUGsrBw82KW2/Start-Building-App.

## Running the code

Run `npm i` to install the dependencies.

Run `npm run dev` to start the development server.

## AgentOps MIS live backend

This UI is wired to the local AgentOps MIS backend through the Vite proxy:

```text
/mis-api/* -> http://127.0.0.1:8787/api/*
```

Set `VITE_AGENTOPS_PROXY_TARGET=http://127.0.0.1:<port>` when an isolated
smoke or customer deployment runs the MIS backend on a non-default port.

Run the MIS backend first:

```bash
cd ../..
python3 server.py
```

Then run this UI:

```bash
npm run dev -- --host 127.0.0.1 --port 19000
```

Live-connected pages include `/workspace`, `/workspace/tasks`, `/workspace/tasks/:id`, `/workspace/agents`, `/workspace/agents/:id`, `/admin`, `/workspace/runs`, `/workspace/runs/:id`, `/workspace/connectors`, `/workspace/evaluations`, `/workspace/tool-calls`, `/workspace/external-bases/notion`, `/workspace/templates`, and `/workspace/audit`; legacy `/admin/*` task/run and admin-operations deep links redirect to their workspace routes.

Browser smoke:

```bash
python3 scripts/vite_playwright_snapshot_smoke.py
```
