# Start Building App

This is a code bundle for Start Building App. The original project is available at https://www.figma.com/design/jVwiVjVKZJlUGsrBw82KW2/Start-Building-App.

## Running the code

Run `npm i` to install the dependencies.

Run `npm run dev` to start the development server.

## AgentOps MIS live backend

Free Local defaults to the local Python compatibility backend through the Vite
proxy:

```text
/mis-api/* -> http://127.0.0.1:8787/api/*
```

Run the MIS backend first:

```bash
cd ../..
python3 server.py
```

Then run this UI:

```bash
npm run dev -- --host 127.0.0.1 --port 19000
```

Live-connected pages include `/workspace`, `/workspace/tasks`, `/workspace/agents`, `/admin`, `/admin/runs`, `/admin/runs/:id`, `/admin/connectors`, `/admin/tasks/:id`, and `/admin/agents/:id`.

For the commercial Next.js/PostgreSQL control plane, use the existing
deployment and control-plane modes:

```bash
VITE_AGENTOPS_DEPLOYMENT_MODE=production \
VITE_AGENTOPS_CONTROL_PLANE_MODE=postgres \
npm run build
```

That build uses `/api/mis` and does not register the Python Vite proxy.
Production, shared, and hosted builds fail closed if configured for proxy mode,
`/mis-api`, a credential-bearing URL, or a non-HTTPS absolute API URL.
