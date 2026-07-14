# Private Host Worker Machine Read Acceptance

## Product Slice

The packaged Host CLI can read Worker status, fleet, adapter readiness, and
stuck-task telemetry after Human Authentication is enabled. It does not reuse a
browser Session and does not grant Agent-bound credentials installation-wide
visibility.

## Route Contract

| Consumer | Route family | Credential |
| --- | --- | --- |
| Browser Workspace | `/api/workers/*` | Human Session |
| Packaged Host CLI | `/api/agent-gateway/host-workers/*` | Host machine credential |
| Remote Agent/Worker | scoped `/api/agent-gateway/tasks`, runs and evidence | bound enrollment/Session token |

The Host read routes are:

- `GET /api/agent-gateway/host-workers/status`
- `GET /api/agent-gateway/host-workers/fleet`
- `GET /api/agent-gateway/host-workers/adapter-readiness`
- `GET /api/agent-gateway/host-workers/stuck-tasks`

All four return `auth.host_machine_only:true`, `safety.read_only:true`,
`safety.ledger_mutated:false`, and `token_omitted:true`. Agent-bound enrollment
and Session tokens receive `403 host_machine_credential_required`, including
when they have `tasks:read`.

## Verification

```bash
python3 -m py_compile server.py agentops_mis_cli/agentops.py scripts/private_host_worker_machine_read_smoke.py
python3 scripts/private_host_worker_machine_read_smoke.py
python3 scripts/human_browser_auth_smoke.py
python3 scripts/agentops_worker_status_smoke.py
python3 scripts/agentops_worker_fleet_smoke.py
python3 scripts/release_evidence_packet_smoke.py
git diff --check
```

The isolated Private Host smoke proves:

- a Host machine key remains rejected by the browser `/api/workers/status`
  route with `401 human_auth_required`;
- the four new machine routes return `200` to the Host credential;
- `agentops worker status|fleet|readiness|stuck` use those routes;
- bound Agent tokens and short-lived Sessions receive the expected `403`;
- missing or incorrect Host machine credentials fail closed; the normal Private
  Host startup guard refuses to listen without `AGENTOPS_API_KEY`, and the route
  retains `503 host_machine_credential_not_configured` as defense in depth;
- ledger table counts and bound credential `last_used_at` values do not change;
- no fixture credential appears in response, CLI, server, or smoke output;
- no real Hermes/OpenClaw execution occurs.

## Known Limits

- This surface is intentionally Host-wide and is not a remote Agent fleet API.
- Worker logs and all Worker write/recovery commands remain on their existing
  Human/Admin control paths.
- `agentops doctor` and loop-driver scoped readiness keep their existing
  contracts; they are not silently upgraded to Host-wide visibility here.

## Current Result

Validated locally on 2026-07-14:

- Private Host machine-read smoke: pass, including four CLI commands, Human
  Session isolation, Agent token/Session `403`, missing-key startup failure,
  unchanged ledger counts, and unchanged rejected-credential usage timestamps.
- Agent Gateway Session, scoped-read, and CLI doctor regressions: pass on an
  isolated SQLite database and loopback server.
- Existing Worker status/fleet, Human Auth, account Workspace UI, bundle,
  release-consumer, release-evidence, Python compile, secret scan, and diff
  checks: pass.
- Live Hermes/OpenClaw execution: not called by this read-only slice.
